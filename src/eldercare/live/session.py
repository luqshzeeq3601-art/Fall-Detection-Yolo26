"""One live detection session: capture -> frozen fall pipeline -> annotated MJPEG frames.

Runs on its own thread. Each processed frame is annotated and JPEG-encoded for the
stream endpoint; confirmed falls are persisted through ``FallIncidentBridge`` with
keyframes from a short frame buffer, then announced over the event callback.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from eldercare.fall_engine.state_machine.states import FallEvent
from eldercare.live.annotate import annotate_frame
from eldercare.live.engine import FallInferenceEngine, load_pose_model
from eldercare.live.sources import ResolvedSource

LOG = logging.getLogger("eldercare.live.session")

FRAME_WIDTH = 640
INFERENCE_FPS = 15.0
JPEG_QUALITY = 78
# Keyframe i is captured KEYFRAME_OFFSETS_SEC[i] seconds before the alert (alert first).
KEYFRAME_OFFSETS_SEC: tuple[float, ...] = (0.0, 1.5, 3.0)
HEARTBEAT_SEC = 2.0
LATENCY_WINDOW = 120
TRACE_STEP_SEC = 0.2
TRACE_POINTS = 300  # one minute of fall-likelihood history

EventSink = Callable[[str, str, "str | None", dict[str, Any]], None]
StatusSink = Callable[[str, str, "datetime | None"], None]
FallSink = Callable[[FallEvent, list[np.ndarray]], "str | None"]


@dataclass(frozen=True)
class SessionOptions:
    fall_threshold: float | None = None
    min_down_sec: float | None = None
    show_skeleton: bool = True
    show_bbox: bool = True
    blur_faces: bool = False
    loop: bool = False


@dataclass
class SessionStatus:
    camera_id: str
    source_type: str
    source: str
    source_label: str
    phase: str = "starting"  # starting | running | finished | stopped | error
    error: str | None = None
    detector_ready: bool = False
    state: str = "NO_PERSON"  # NO_PERSON | NORMAL | FALLING | FALL_DETECTED
    confidence: float = 0.0
    track_id: int | None = None
    fall_likelihood: float | None = None
    video_time: float = 0.0
    frames: int = 0
    falls: int = 0
    last_incident_id: str | None = None
    fps: float = 0.0
    latency_avg_ms: float = 0.0
    latency_p95_ms: float = 0.0
    duration: float | None = None  # file sources only, seconds
    detections: list[dict[str, Any]] = field(default_factory=list)
    trace: list[tuple[float, float]] = field(default_factory=list)  # (video s, likelihood)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["detections"] = [dict(d) for d in self.detections]
        data["trace"] = [list(p) for p in self.trace]
        return data


def _resize(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w == FRAME_WIDTH:
        return frame
    return cv2.resize(frame, (FRAME_WIDTH, max(1, round(h * FRAME_WIDTH / w))))


def _open_capture(source: ResolvedSource) -> cv2.VideoCapture:
    if source.source_type == "webcam":
        assert source.webcam_index is not None
        if sys.platform == "win32":
            cap = cv2.VideoCapture(source.webcam_index, cv2.CAP_DSHOW)
            if cap.isOpened():
                return cap
            cap.release()
        return cv2.VideoCapture(source.webcam_index)
    assert source.path is not None
    return cv2.VideoCapture(str(source.path))


def scan_webcams(max_index: int, skip: set[int]) -> list[dict[str, Any]]:
    """Probe webcam indexes 0..max_index; ``skip`` holds indexes already streaming."""
    found: list[dict[str, Any]] = []
    for index in range(max_index + 1):
        if index in skip:
            found.append({"index": index, "width": None, "height": None, "in_use": True})
            continue
        cap = _open_capture(ResolvedSource("webcam", str(index), f"Camera {index}", index))
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            found.append({"index": index, "width": int(w), "height": int(h), "in_use": False})
        finally:
            cap.release()
    return found


def probe_source(source: ResolvedSource) -> tuple[bool, str]:
    """Open the source and read one frame; return (ok, human-readable detail)."""
    cap = _open_capture(source)
    try:
        if not cap.isOpened():
            return False, f"Could not open {source.label}."
        ok, frame = cap.read()
        if not ok or frame is None:
            return False, f"{source.label} opened but returned no frames."
        h, w = frame.shape[:2]
        return True, f"{source.label} delivered a {w}x{h} frame."
    finally:
        cap.release()


class LiveSession:
    """Owns the capture thread for one camera."""

    def __init__(
        self,
        camera_id: str,
        source: ResolvedSource,
        options: SessionOptions,
        emit: EventSink,
        set_camera_status: StatusSink,
        record_fall: FallSink,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.options = options
        self._emit = emit
        self._set_camera_status = set_camera_status
        self._record_fall = record_fall
        self._stop = threading.Event()
        self._frame_cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._frame_seq = 0
        self._latencies: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._inference_times: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._lock = threading.Lock()
        self.status = SessionStatus(
            camera_id=camera_id,
            source_type=source.source_type,
            source=source.ref,
            source_label=source.label,
        )
        self._thread = threading.Thread(target=self._run, name=f"live-{camera_id}", daemon=True)

    # -- control -----------------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._frame_cond:
            self._frame_cond.notify_all()
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout)

    @property
    def active(self) -> bool:
        return self._thread.is_alive() and not self._stop.is_set()

    def snapshot_status(self) -> dict[str, Any]:
        with self._lock:
            return self.status.as_dict()

    # -- frames ------------------------------------------------------------------

    def latest_jpeg(self) -> bytes | None:
        with self._frame_cond:
            return self._jpeg

    def wait_frame(self, last_seq: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        """Block until a frame newer than ``last_seq`` exists (or timeout/stop)."""
        with self._frame_cond:
            if self._frame_seq == last_seq and not self._stop.is_set():
                self._frame_cond.wait(timeout)
            return self._frame_seq, self._jpeg

    def _publish(self, frame: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return
        with self._frame_cond:
            self._jpeg = buf.tobytes()
            self._frame_seq += 1
            self._frame_cond.notify_all()

    # -- worker ------------------------------------------------------------------

    def _update(self, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self.status, key, value)

    def _fail(self, message: str) -> None:
        LOG.warning("Live session %s failed: %s", self.camera_id, message)
        self._update(phase="error", error=message)
        self._set_camera_status(self.camera_id, "offline", None)
        self._emit("camera.offline", self.camera_id, None, {"reason": message})

    def _run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:  # noqa: BLE001 - surface as session error, never crash API
            LOG.exception("Live session %s crashed", self.camera_id)
            self._fail(f"Unexpected error: {exc}")

    def _run_inner(self) -> None:
        cap = _open_capture(self.source)
        if not cap.isOpened():
            cap.release()
            self._fail(f"Could not open {self.source.label}.")
            return

        model = load_pose_model()
        engine = FallInferenceEngine(
            fall_threshold=self.options.fall_threshold,
            min_down_sec=self.options.min_down_sec,
            target_fps=INFERENCE_FPS,
        )
        detector_ready = model is not None and engine.ready
        self._update(
            phase="running",
            detector_ready=detector_ready,
            error=None if detector_ready else "Model weights missing: no detection runs.",
        )
        self._set_camera_status(self.camera_id, "online", datetime.now(timezone.utc))
        self._emit("camera.online", self.camera_id, None, {"source": self.source.label})

        is_file = self.source.source_type == "file"
        src_fps = cap.get(cv2.CAP_PROP_FPS) if is_file else 0.0
        frame_period = 1.0 / src_fps if src_fps and 1.0 < src_fps < 120.0 else 1.0 / 30.0
        if is_file:
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count and frame_count > 0:
                self._update(duration=round(frame_count * frame_period, 2))
        buffer_len = int(max(KEYFRAME_OFFSETS_SEC) * (1.0 / frame_period)) + 10
        frames: deque[tuple[float, np.ndarray]] = deque(maxlen=buffer_len)
        t0 = time.perf_counter()
        last_heartbeat = 0.0
        loop_offset = 0.0
        last_src_t = 0.0
        frame_count = 0
        read_failures = 0

        try:
            while not self._stop.is_set():
                tick = time.perf_counter()
                ok, raw = cap.read()
                if not ok or raw is None:
                    if is_file and self.options.loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        loop_offset = last_src_t + frame_period
                        continue
                    if is_file:
                        self._update(phase="finished")
                        break
                    read_failures += 1
                    if read_failures > 30:
                        self._fail(f"{self.source.label} stopped delivering frames.")
                        return
                    time.sleep(0.05)
                    continue
                read_failures = 0
                frame = _resize(raw)
                if is_file:
                    src_t = loop_offset + cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                else:
                    src_t = tick - t0
                last_src_t = src_t
                frames.append((src_t, frame))

                result = None
                if detector_ready:
                    before = engine.last_inference_timestamp
                    started = time.perf_counter()
                    result = engine.process_frame(frame, model, timestamp=src_t)
                    if engine.last_inference_timestamp != before:
                        now = time.perf_counter()
                        self._latencies.append((now - started) * 1000.0)
                        self._inference_times.append(now)

                shown = annotate_frame(
                    frame=frame,
                    keypoints=result.keypoints if result else None,
                    bbox=result.bbox if result else None,
                    track_id=result.track_id if result else -1,
                    state=result.state if result else "NORMAL",
                    privacy_blur=self.options.blur_faces,
                    show_skeleton=self.options.show_skeleton,
                    show_bbox=self.options.show_bbox,
                )
                self._publish(shown)
                frame_count += 1
                self._update_metrics(result, src_t, frame_count)

                if result is not None and result.fall_event is not None:
                    self._handle_fall(result.fall_event, result.track_id, frames, src_t)

                if tick - last_heartbeat >= HEARTBEAT_SEC:
                    last_heartbeat = tick
                    self._set_camera_status(self.camera_id, "online", datetime.now(timezone.utc))

                if is_file:
                    time.sleep(max(0.0, frame_period - (time.perf_counter() - tick)))
        finally:
            cap.release()
            with self._lock:
                if self.status.phase == "running":
                    self.status.phase = "stopped"
            self._set_camera_status(self.camera_id, "idle", None)
            self._emit("camera.offline", self.camera_id, None, {"reason": "stream stopped"})
            with self._frame_cond:
                self._frame_cond.notify_all()

    def _update_metrics(self, result: Any, src_t: float, frame_count: int) -> None:
        times = list(self._inference_times)
        fps = 0.0
        if len(times) >= 2 and times[-1] > times[0]:
            fps = (len(times) - 1) / (times[-1] - times[0])
        lat = sorted(self._latencies)
        avg = sum(lat) / len(lat) if lat else 0.0
        p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))] if lat else 0.0
        if result is None or result.track_id < 0:
            state, conf, track, likelihood = "NO_PERSON", 0.0, None, None
        else:
            state, conf, track = result.state, result.confidence, result.track_id
            likelihood = conf if state != "NORMAL" else 1.0 - conf
        with self._lock:
            trace = self.status.trace
            if trace and src_t < trace[-1][0]:
                trace.clear()  # looped video restarted the clock
            if not trace or src_t - trace[-1][0] >= TRACE_STEP_SEC:
                trace.append((round(src_t, 2), round(likelihood or 0.0, 3)))
                del trace[:-TRACE_POINTS]
        self._update(
            state=state,
            confidence=round(conf, 4),
            track_id=track,
            fall_likelihood=None if likelihood is None else round(likelihood, 4),
            video_time=round(src_t, 2),
            frames=frame_count,
            fps=round(fps, 2),
            latency_avg_ms=round(avg, 2),
            latency_p95_ms=round(p95, 2),
        )

    def _handle_fall(
        self,
        event: FallEvent,
        track_id: int,
        frames: deque[tuple[float, np.ndarray]],
        src_t: float,
    ) -> None:
        keyframes = [
            min(frames, key=lambda tf: abs(tf[0] - (src_t - off)))[1]
            for off in KEYFRAME_OFFSETS_SEC
        ]
        # Pipeline timestamps are source-relative; incidents use wall-clock time,
        # keeping the gaps between onset, descent and confirmation.
        now = time.time()
        stamped = replace(
            event,
            camera_id=self.camera_id,
            confirmed_timestamp=now,
            candidate_timestamp=now - (event.confirmed_timestamp - event.candidate_timestamp),
            down_start_timestamp=now - (event.confirmed_timestamp - event.down_start_timestamp),
        )
        incident_id: str | None = None
        try:
            incident_id = self._record_fall(stamped, keyframes)
        except Exception:  # noqa: BLE001 - the alert must still go out
            LOG.exception("Persisting fall for %s failed", self.camera_id)
        with self._lock:
            self.status.falls += 1
            self.status.last_incident_id = incident_id
            self.status.detections.append(
                {
                    "video_time": round(src_t, 2),
                    "incident_id": incident_id,
                    "fall_score": round(float(event.confidence), 3),
                    "track_id": track_id,
                }
            )
        self._emit(
            "fall.confirmed",
            self.camera_id,
            incident_id,
            {
                "track_id": str(track_id),
                "fall_score": float(event.confidence),
                "video_time": round(src_t, 2),
                "source": self.source.label,
                "persisted": incident_id is not None,
            },
        )
