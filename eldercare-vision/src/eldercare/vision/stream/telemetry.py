"""Lightweight capture telemetry aggregating existing component state (P1-006).

``None``-means-unknown rule
---------------------------
Every ``None`` in :class:`CaptureSnapshot` means *unknown / not attached*,
never zero and never a guess. Unattached components read as ``None`` (not
``0`` — zero would claim "measured empty"); ``capture_fps`` is ``None``
until at least two in-window frames exist (a single frame is not a rate, and
this module NEVER fabricates one).

FPS definition + boundary
-------------------------
``capture_fps = (# frame timestamps with ts > now - fps_window_seconds)
  / fps_window_seconds``. The window bound is STRICT ``>``: a frame stamped
at exactly ``now - window`` is excluded (mirrors the strict-``>`` honesty of
the health monitor thresholds). ``< 2`` in-window timestamps yield ``None``.
The result is a plain finite ``float`` by construction (``count >= 2`` over a
finite ``window > 0``), so ``json.dumps(to_dict(), allow_nan=False)`` always
passes — asserted in tests on empty, populated, and post-prune snapshots.

Ownership map
-------------
Telemetry OWNS only its frame-timestamp deque + ``frames_received`` counter.
Everything else (queue submitted/dropped/depth, health state/last_frame_at,
reconnect attempts/consecutive_failures) is read LIVE through the components'
public getters at snapshot time and never stored, configured, or mutated.

Lock-ordering rule
------------------
One ``threading.Lock`` guards ONLY the owned deque/counter. Component getters
are NEVER called while holding the telemetry lock: ``snapshot()`` copies the
owned state under the lock (acquire-copy-release), releases it, and only then
reads components into locals before assembling the snapshot. ``note_frame()``
touches owned state only and calls no component code at all. No I/O, logging,
or callbacks happen inside any critical section.

Frame-timestamp policy
----------------------
``note_frame`` accepts out-of-order (older) timestamps and then prunes —
frames are observations, not state, so unlike the health monitor there is no
ignore rule for clock jitter (justified: dropping an observation would
under-count a real delivery; window pruning already bounds its influence).
Pruning is relative to the just-noted timestamp (``ts <= ts - window`` are
dropped); ``snapshot()`` itself is side-effect-free and never prunes.

What is NOT here (later phases, never this module)
--------------------------------------------------
Prometheus/OpenTelemetry metrics, MQTT publishing, DB persistence, CPU/GPU
hardware stats, dashboard code, and Phase-2 inference telemetry. This module
exposes the stable typed snapshot those consumers will read later.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # precise public-API hints with zero runtime import cost
    from eldercare.vision.stream.health import StreamHealthMonitor
    from eldercare.vision.stream.queue import LatestFrameQueue
    from eldercare.vision.stream.reconnect import ReconnectController

#: Hard safety cap on retained frame timestamps. Bounds memory even when the
#: clock jumps or stalls (a frozen clock disables window pruning, so without
#: a cap a fast producer could grow the deque without bound). 16384 float
#: timestamps (~128 KiB plus deque overhead) are negligible, while far above
#: any plausible 5 s capture window (even 1000 fps × 5 s = 5000 frames).
MAX_FRAME_TIMESTAMPS: int = 16384


def _check_window(value: float | int, name: str) -> float:
    """Validate the FPS window; return it as ``float``.

    Raises:
        ValueError: if boolean, non-numeric, non-finite, or ``<= 0``.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a finite float > 0, got {value!r}")
    return float(value)


def _check_timestamp(value: float | int, name: str) -> float:
    """Validate a timestamp; return it as ``float``.

    Mirrors the health monitor's timestamp discipline.

    Raises:
        ValueError: if boolean, non-numeric, non-finite, or negative.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite float >= 0, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class CaptureSnapshot:
    """Stable point-in-time capture contract (field names are the P1-006 API).

    ``camera_id``: stable camera identity (mirrors ``CameraConfig.camera_id``).
    ``captured_at``: snapshot clock time in seconds (the ``now`` used).
    ``capture_fps``: measured frames-per-second over the trailing
        ``fps_window_seconds`` window, or ``None`` when unknown (fewer than 2
        in-window frames — NEVER a fabricated rate).
    ``frames_received``: telemetry-owned monotonic frame count (all notes
        ever accepted, including out-of-order ones).
    ``queue_submitted``: live ``LatestFrameQueue.submitted`` total, or
        ``None`` when no queue is attached (unknown, not zero).
    ``queue_dropped``: live ``LatestFrameQueue.dropped`` total, or ``None``
        when unattached.
    ``queue_depth``: live ``LatestFrameQueue.depth``, or ``None`` when
        unattached.
    ``reconnect_attempts``: live ``ReconnectController.attempts`` total, or
        ``None`` when unattached.
    ``reconnect_failures``: live ``ReconnectController.consecutive_failures``
        (mirrors the controller's consecutive counter — NOT lifetime
        failures), or ``None`` when unattached.
    ``health_state``: lowercase health state value (``"unknown"`` /
        ``"online"`` / ``"degraded"`` / ``"offline"``), or ``None`` when no
        health monitor is attached.
    ``last_frame_at``: timestamp of the newest frame the health monitor
        accepted, or ``None`` when unattached / no frame recorded yet.
    ``seconds_since_last_frame``: ``captured_at - last_frame_at``, or
        ``None`` when unattached / no frame recorded yet (unknown, not zero).
    """

    camera_id: str
    captured_at: float
    capture_fps: float | None
    frames_received: int
    queue_submitted: int | None
    queue_dropped: int | None
    queue_depth: int | None
    reconnect_attempts: int | None
    reconnect_failures: int | None
    health_state: str | None
    last_frame_at: float | None
    seconds_since_last_frame: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe primitives only; ``None``s preserved, never stringified."""
        return {
            "camera_id": self.camera_id,
            "captured_at": self.captured_at,
            "capture_fps": self.capture_fps,
            "frames_received": self.frames_received,
            "queue_submitted": self.queue_submitted,
            "queue_dropped": self.queue_dropped,
            "queue_depth": self.queue_depth,
            "reconnect_attempts": self.reconnect_attempts,
            "reconnect_failures": self.reconnect_failures,
            "health_state": self.health_state,
            "last_frame_at": self.last_frame_at,
            "seconds_since_last_frame": self.seconds_since_last_frame,
        }


class CaptureTelemetry:
    """Thread-safe aggregator of capture-side observable state.

    Owns ONLY a frame-timestamp deque + ``frames_received`` counter.
    Component references (queue/health/reconnect) are READ-ONLY handles:
    this class never mutates, configures, or stores derived component state.

    Args:
        camera_id: Stable camera identity (never rendered with secrets —
            ids are pattern-validated upstream; only scalars render here).
        queue: Read-only ``LatestFrameQueue`` handle (or ``None``).
        health: Read-only ``StreamHealthMonitor`` handle (or ``None``).
        reconnect: Read-only ``ReconnectController`` handle (or ``None``).
        clock: Zero-argument seconds source (defaults to
            :func:`time.monotonic`).
        fps_window_seconds: Trailing window for the FPS rate; must be a
            finite ``float > 0``.

    Raises:
        ValueError: if ``fps_window_seconds`` is not a finite float ``> 0``.
    """

    def __init__(
        self,
        camera_id: str,
        queue: LatestFrameQueue[Any] | None = None,
        health: StreamHealthMonitor | None = None,
        reconnect: ReconnectController | None = None,
        clock: Callable[[], float] = time.monotonic,
        fps_window_seconds: float = 5.0,
    ) -> None:
        self._camera_id: str = camera_id
        self._queue = queue
        self._health = health
        self._reconnect = reconnect
        self._clock: Callable[[], float] = clock
        self._window: float = _check_window(fps_window_seconds, "fps_window_seconds")
        self._lock = threading.Lock()
        self._frame_times: deque[float] = deque()
        self._frames_received: int = 0

    @property
    def camera_id(self) -> str:
        """Stable camera identity this telemetry aggregates for."""
        return self._camera_id

    @property
    def fps_window_seconds(self) -> float:
        """Trailing window (seconds) used for the FPS rate."""
        return self._window

    @property
    def frames_received(self) -> int:
        """Monotonic count of all accepted ``note_frame`` calls."""
        with self._lock:
            return self._frames_received

    @property
    def frame_window_size(self) -> int:
        """Number of timestamps currently retained in the FPS window deque.

        Documented introspection hook for the bounded-memory test; no other
        internals are exposed.
        """
        with self._lock:
            return len(self._frame_times)

    def note_frame(self, timestamp: float | None = None) -> None:
        """Record one delivered frame observation.

        ``None`` reads the injected ``clock()``. Out-of-order (older)
        timestamps are ACCEPTED (frames are observations, not state — unlike
        the health monitor there is no ignore rule); entries at or below
        ``timestamp - window`` are then pruned, and the hard
        ``MAX_FRAME_TIMESTAMPS`` cap is enforced. ``frames_received`` is
        incremented for every accepted note.

        Raises:
            ValueError: if ``timestamp`` is non-numeric, non-finite, or negative.
        """
        frame_at = _check_timestamp(self._clock() if timestamp is None else timestamp, "timestamp")
        cutoff = frame_at - self._window
        with self._lock:
            self._frame_times.append(frame_at)
            while self._frame_times and self._frame_times[0] <= cutoff:
                self._frame_times.popleft()
            while len(self._frame_times) > MAX_FRAME_TIMESTAMPS:
                self._frame_times.popleft()
            self._frames_received += 1

    def snapshot(self, now: float | None = None) -> CaptureSnapshot:
        """Assemble a :class:`CaptureSnapshot` WITHOUT mutating any component.

        Component getters are read WITHOUT holding the telemetry lock
        (acquire-copy-release of owned state first; see the module lock
        rule). FPS counts owned timestamps with ``ts > now - window``; fewer
        than 2 in-window timestamps yield ``None``. The returned snapshot is
        a frozen value — repeated calls are side-effect-free.

        Raises:
            ValueError: if ``now`` is non-numeric, non-finite, or negative.
        """
        current = _check_timestamp(self._clock() if now is None else now, "now")
        with self._lock:
            window_times = tuple(self._frame_times)
            received = self._frames_received
        cutoff = current - self._window
        in_window = sum(1 for ts in window_times if ts > cutoff)
        fps = in_window / self._window if in_window >= 2 else None
        # Lock released before ANY component read (lock-ordering discipline).
        queue_submitted = self._queue.submitted if self._queue is not None else None
        queue_dropped = self._queue.dropped if self._queue is not None else None
        queue_depth = self._queue.depth if self._queue is not None else None
        reconnect_attempts = self._reconnect.attempts if self._reconnect is not None else None
        reconnect_failures = (
            self._reconnect.consecutive_failures if self._reconnect is not None else None
        )
        if self._health is None:
            health_state: str | None = None
            last_frame_at: float | None = None
            seconds_since: float | None = None
        else:
            last_frame_at = self._health.last_frame_at
            health_state = self._health.state.value
            seconds_since = current - last_frame_at if last_frame_at is not None else None
        return CaptureSnapshot(
            camera_id=self._camera_id,
            captured_at=current,
            capture_fps=fps,
            frames_received=received,
            queue_submitted=queue_submitted,
            queue_dropped=queue_dropped,
            queue_depth=queue_depth,
            reconnect_attempts=reconnect_attempts,
            reconnect_failures=reconnect_failures,
            health_state=health_state,
            last_frame_at=last_frame_at,
            seconds_since_last_frame=seconds_since,
        )

    def __repr__(self) -> str:
        # Numeric/id/enum only: camera_id + counters + locally computed fps +
        # scalar component reads. Payloads/URLs can never appear — telemetry
        # holds no frames and no config URLs by construction. Component reads
        # happen WITHOUT the telemetry lock (same discipline as snapshot).
        with self._lock:
            camera_id = self._camera_id
            received = self._frames_received
            window_times = tuple(self._frame_times)
        window = self._window  # immutable after __init__: no lock needed
        cutoff = self._clock() - window
        in_window = sum(1 for ts in window_times if ts > cutoff)
        fps: float | None = in_window / window if in_window >= 2 else None
        depth = self._queue.depth if self._queue is not None else None
        health = self._health.state.value if self._health is not None else None
        return (
            f"CaptureTelemetry(camera_id={camera_id!r}, "
            f"frames_received={received!r}, "
            f"fps={fps!r}, "
            f"depth={depth!r}, "
            f"health={health!r})"
        )


__all__ = ["MAX_FRAME_TIMESTAMPS", "CaptureSnapshot", "CaptureTelemetry"]
