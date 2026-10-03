"""Process-wide registry of live sessions plus host telemetry sampling."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import numpy as np
import psutil
from sqlalchemy.orm import Session, sessionmaker

from eldercare.api.schemas import WebSocketEvent
from eldercare.api.workspace import load_workspace_settings
from eldercare.api.ws import ConnectionManager
from eldercare.db.models import Camera, CameraSource
from eldercare.fall_engine.state_machine.states import FallEvent
from eldercare.incidents.bridge import FallIncidentBridge
from eldercare.live.session import LiveSession, SessionOptions, probe_source, scan_webcams
from eldercare.live.sources import ResolvedSource, SourceCatalog, SourceError

LOG = logging.getLogger("eldercare.live.manager")

SAMPLE_INTERVAL_SEC = 2.0
MAX_WEBCAM_SCAN = 4
VIDEO_ANALYSIS_CAMERA = ("video-analysis", "Video analysis")
HISTORY_POINTS = 150  # 5 minutes at 2 s


class CameraBusyError(RuntimeError):
    """A stream is already running for this camera."""


def _gpu_sample() -> dict[str, float | None]:
    """GPU utilisation/memory via NVML when available; None values otherwise."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return {
            "gpu_percent": float(util.gpu),
            "gpu_memory_used_mb": round(mem.used / 2**20, 1),
            "gpu_memory_total_mb": round(mem.total / 2**20, 1),
        }
    except Exception:  # noqa: BLE001 - no NVIDIA GPU / driver
        return {"gpu_percent": None, "gpu_memory_used_mb": None, "gpu_memory_total_mb": None}


class LiveManager:
    """Starts/stops per-camera sessions and keeps a rolling telemetry history."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        catalog: SourceCatalog,
        connection_manager: ConnectionManager,
        loop: asyncio.AbstractEventLoop,
        bridge_factory: Callable[[], FallIncidentBridge],
    ) -> None:
        self._session_factory = session_factory
        self.catalog = catalog
        self._ws = connection_manager
        self._loop = loop
        self._bridge_factory = bridge_factory
        self._bridge: FallIncidentBridge | None = None
        self._sessions: dict[str, LiveSession] = {}
        self._lock = threading.Lock()
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY_POINTS)
        self._stop = threading.Event()
        self._sampler = threading.Thread(target=self._sample_loop, name="telemetry", daemon=True)
        psutil.cpu_percent(None)  # prime the counter
        self._sampler.start()

    # -- callbacks used by sessions ---------------------------------------------

    def emit(
        self, event_type: str, camera_id: str, incident_id: str | None, payload: dict[str, Any]
    ) -> None:
        event = WebSocketEvent(
            event_type=event_type, camera_id=camera_id, incident_id=incident_id, payload=payload
        )
        try:
            asyncio.run_coroutine_threadsafe(self._ws.broadcast(event), self._loop)
        except RuntimeError:  # loop closed during shutdown
            pass

    def _set_camera_status(self, camera_id: str, status: str, frame_at: datetime | None) -> None:
        try:
            with self._session_factory() as db:
                camera = db.get(Camera, camera_id)
                if camera is None:
                    return
                camera.status = status
                now = datetime.now(timezone.utc)
                camera.last_heartbeat_at = now
                if frame_at is not None:
                    camera.last_frame_at = frame_at
                db.commit()
        except Exception:  # noqa: BLE001 - health bookkeeping must not stop video
            LOG.exception("Camera status update failed for %s", camera_id)

    def _record_fall(self, event: FallEvent, keyframes: list[np.ndarray]) -> str | None:
        if self._bridge is None:
            self._bridge = self._bridge_factory()
        return self._bridge.handle_fall_event(event, keyframes).id

    # -- sources -----------------------------------------------------------------

    def resolve_for_camera(
        self, camera_id: str, source_type: str | None, source: str | None, loop: bool | None
    ) -> tuple[ResolvedSource, bool]:
        """Resolve the given source (saving it) or the camera's stored one."""
        with self._session_factory() as db:
            if db.get(Camera, camera_id) is None:
                raise KeyError(camera_id)
            stored = db.get(CameraSource, camera_id)
            if source_type is None or source is None:
                if stored is None:
                    raise SourceError("No video source is configured for this camera.")
                return self.catalog.resolve(stored.source_type, stored.source), (
                    stored.loop if loop is None else loop
                )
            resolved = self.catalog.resolve(source_type, source)
            if stored is None:
                stored = CameraSource(camera_id=camera_id, source_type=source_type, source=source)
                db.add(stored)
            stored.source_type = source_type
            stored.source = source
            if loop is not None:
                stored.loop = loop
            db.commit()
            return resolved, stored.loop

    def scan_cameras(self) -> list[dict[str, Any]]:
        """Webcams that open and deliver a frame (streaming ones are reported in use)."""
        with self._lock:
            busy = {
                s.source.webcam_index: s.camera_id
                for s in self._sessions.values()
                if s.active and s.source.webcam_index is not None
            }
        found = scan_webcams(MAX_WEBCAM_SCAN, set(busy))
        for cam in found:
            cam["camera_id"] = busy.get(cam["index"], f"webcam-{cam['index']}")
            cam["label"] = f"Camera {cam['index']}" + (" (default)" if cam["index"] == 0 else "")
        return found

    def camera_for_source(self, source_type: str, source: str) -> str:
        """Camera row that incidents from this source are filed under (created on demand).

        Webcam N maps to ``webcam-N``; every video file maps to one "Video analysis" camera,
        so recorded footage never mixes with a real room's incident history.
        """
        resolved = self.catalog.resolve(source_type, source)
        if resolved.source_type == "webcam":
            camera_id, name = f"webcam-{resolved.webcam_index}", f"Webcam {resolved.webcam_index}"
        else:
            camera_id, name = VIDEO_ANALYSIS_CAMERA
        with self._session_factory() as db:
            if db.get(Camera, camera_id) is None:
                db.add(Camera(id=camera_id, name=name, status="idle"))
                db.commit()
        return camera_id

    def test_source(self, source_type: str, source: str) -> tuple[bool, str]:
        resolved = self.catalog.resolve(source_type, source)
        if resolved.source_type == "webcam":
            with self._lock:
                for session in self._sessions.values():
                    if session.active and session.source.ref == resolved.ref:
                        busy = f"{resolved.label} is streaming for camera {session.camera_id}."
                        return True, busy
        return probe_source(resolved)

    # -- sessions ----------------------------------------------------------------

    def start(
        self,
        camera_id: str,
        source_type: str | None = None,
        source: str | None = None,
        loop: bool | None = None,
    ) -> dict[str, Any]:
        resolved, do_loop = self.resolve_for_camera(camera_id, source_type, source, loop)
        with self._session_factory() as db:
            settings = load_workspace_settings(db)
        options = SessionOptions(
            fall_threshold=settings.fall_threshold,
            min_down_sec=settings.min_down_sec,
            show_skeleton=settings.show_skeleton,
            show_bbox=settings.show_bbox,
            blur_faces=settings.blur_faces,
            loop=do_loop,
        )
        with self._lock:
            existing = self._sessions.get(camera_id)
            if existing is not None and existing.active:
                raise CameraBusyError(camera_id)
            if resolved.source_type == "webcam":
                for other in self._sessions.values():
                    if other.active and other.source.ref == resolved.ref:
                        raise CameraBusyError(other.camera_id)
            session = LiveSession(
                camera_id=camera_id,
                source=resolved,
                options=options,
                emit=self.emit,
                set_camera_status=self._set_camera_status,
                record_fall=self._record_fall,
            )
            self._sessions[camera_id] = session
        session.start()
        return session.snapshot_status()

    def stop(self, camera_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(camera_id)
        if session is None:
            return False
        session.stop()
        return True

    def get(self, camera_id: str) -> LiveSession | None:
        with self._lock:
            return self._sessions.get(camera_id)

    def statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.snapshot_status() | {"active": s.active} for s in sessions]

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.stop(timeout=3.0)

    # -- telemetry ---------------------------------------------------------------

    def stream_metrics(self) -> dict[str, Any]:
        """Mean FPS/latency over running sessions that are performing inference."""
        running = [
            s
            for s in self.statuses()
            if s["active"] and s["phase"] == "running" and s["detector_ready"] and s["fps"] > 0
        ]
        if not running:
            return {"active_streams": 0, "fps": 0.0, "latency_avg_ms": 0.0, "latency_p95_ms": 0.0}
        n = len(running)
        return {
            "active_streams": n,
            "fps": round(sum(s["fps"] for s in running) / n, 2),
            "latency_avg_ms": round(sum(s["latency_avg_ms"] for s in running) / n, 2),
            "latency_p95_ms": round(max(s["latency_p95_ms"] for s in running), 2),
        }

    def sample(self) -> dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": psutil.cpu_percent(None),
            "memory_used_gb": round(mem.used / 2**30, 2),
            "memory_total_gb": round(mem.total / 2**30, 2),
            **_gpu_sample(),
            **self.stream_metrics(),
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def latest(self) -> dict[str, Any]:
        """Most recent sampler point (refreshing stream metrics), or a fresh sample.

        Only the sampler thread calls ``psutil.cpu_percent`` after startup, so its
        interval-based readings are not disturbed by API requests.
        """
        if not self._history:
            return self.sample()
        return {**self._history[-1], **self.stream_metrics()}

    def _sample_loop(self) -> None:
        while not self._stop.wait(SAMPLE_INTERVAL_SEC):
            try:
                self._history.append(self.sample())
            except Exception:  # noqa: BLE001
                LOG.exception("Telemetry sample failed")
