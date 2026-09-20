"""Deterministic camera stall/health state machine (P1-004).

States
------
``UNKNOWN → ONLINE ⇄ DEGRADED ⇄ OFFLINE`` — driven only by frame arrivals
(:meth:`StreamHealthMonitor.notify_frame`) and silence timeouts
(:meth:`StreamHealthMonitor.poll`) on an injectable clock. Pure logic:
stdlib only — no video-capture backend, no threads spawned, no reconnect,
no MQTT, no persistence.

Thresholds
----------
``degraded_after`` (default ``2.0`` s) and ``offline_after`` (default
``10.0`` s) with the invariant ``0 < degraded_after < offline_after``.
Silence is ``now - last_frame_at``; when no frame has ever arrived it is
``now - created_at`` (time since the monitor was constructed), so
prolonged pre-first-frame silence also degrades/offlines the monitor
(``UNKNOWN → DEGRADED → OFFLINE``).

Boundary semantics (contract-first)
-----------------------------------
Transitions fire on STRICTLY-greater (``>``); exact equality stays:
``silence == degraded_after`` (resp. ``offline_after``) yields no
transition. Both sides of both thresholds are pinned by tests.

No-duplicate rule
-----------------
Both :meth:`notify_frame` and :meth:`poll` return a
:class:`HealthTransition` ONLY on an actual state change, else ``None``.
Polling twice in the same silent state logs and emits nothing.

Out-of-order policy
-------------------
A frame timestamp OLDER than the recorded ``last_frame_at`` (clock jitter)
is IGNORED: it returns ``None`` and leaves state and ``last_frame_at``
unchanged. Equal timestamps are accepted (not older) but still emit
nothing when the state is already ``ONLINE``.

What this machine does NOT do
-----------------------------
Reconnect/backoff is P1-005; camera events/persistence are later tasks
(see pack ``EVENT_SCHEMA.md`` §2 ``camera.online/degraded/offline``
names — the lowercase state values here stay compatible, but no event
code is emitted by this module). FPS/capture telemetry belongs to P1-006.

Thread-safety
-------------
A single ``threading.Lock`` guards all mutable state (same pattern as
``vision.stream.queue``); the monitor may be called from capture and
consumer threads. No I/O (including logging) happens inside the lock:
transitions are materialised under the lock, then logged after release.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from eldercare.common.logger import get_logger

#: Reason recorded when a frame arrival moves the monitor to ONLINE.
REASON_FRAME_RECEIVED: str = "frame-received"

#: Reason recorded when silence exceeds ``degraded_after``.
REASON_SILENCE_DEGRADED: str = "silence-degraded"

#: Reason recorded when silence exceeds ``offline_after``.
REASON_SILENCE_OFFLINE: str = "silence-offline"

#: Event code emitted (INFO) on actual transitions only.
EVENT_TRANSITION: str = "stream.health.transition"


class CameraHealthState(str, Enum):
    """Health states with lowercase string values for future JSON/event use."""

    UNKNOWN = "unknown"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass(frozen=True)
class HealthTransition:
    """One observed state change."""

    from_state: CameraHealthState
    to_state: CameraHealthState
    reason: str
    timestamp: float


class StreamHealthMonitor:
    """Stall/health signal for one camera.

    Args:
        camera_id: Plain non-empty string identifying the camera. Shape
            validation lives upstream in ``CameraConfig`` (P1-001); this
            layer only requires non-empty.
        degraded_after: Silence seconds after which the camera counts as
            degraded. Must satisfy ``0 < degraded_after``.
        offline_after: Silence seconds after which the camera counts as
            offline. Must satisfy ``degraded_after < offline_after``.
        clock: Zero-argument seconds source for determinism (defaults to
            :func:`time.monotonic`). The construction instant
            (``clock()`` at ``__init__``) anchors pre-first-frame silence.
    """

    def __init__(
        self,
        camera_id: str,
        degraded_after: float = 2.0,
        offline_after: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(camera_id, str) or not camera_id:
            raise ValueError(f"camera_id must be a non-empty string, got {camera_id!r}")
        if not 0 < degraded_after < offline_after:
            raise ValueError(
                "thresholds must satisfy 0 < degraded_after < offline_after, "
                f"got degraded_after={degraded_after!r}, offline_after={offline_after!r}"
            )
        self._camera_id: str = camera_id
        self._degraded_after: float = degraded_after
        self._offline_after: float = offline_after
        self._clock: Callable[[], float] = clock
        self._created_at: float = clock()
        self._lock = threading.Lock()
        self._state: CameraHealthState = CameraHealthState.UNKNOWN
        self._last_frame_at: float | None = None
        self._logger = get_logger(service="vision", component="stream.health", camera_id=camera_id)

    @staticmethod
    def _check_timestamp(value: float | int, name: str) -> float:
        """Validate a timestamp; return it as ``float``.

        Raises:
            ValueError: if non-numeric, non-finite, or negative.
        """
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{name} must be a finite float >= 0, got {value!r}")
        return float(value)

    def notify_frame(self, timestamp: float) -> HealthTransition | None:
        """Record a frame arrival at ``timestamp`` seconds.

        Returns a transition to ``ONLINE`` (reason frame-received) ONLY if
        the previous state was not ``ONLINE``, else ``None``. Timestamps
        older than the recorded ``last_frame_at`` are ignored (``None``,
        state unchanged).

        Raises:
            ValueError: if ``timestamp`` is non-finite or negative.
        """
        frame_at = self._check_timestamp(timestamp, "timestamp")
        with self._lock:
            if self._last_frame_at is not None and frame_at < self._last_frame_at:
                return None  # out-of-order: ignore, state unchanged
            self._last_frame_at = frame_at
            if self._state is CameraHealthState.ONLINE:
                return None
            transition = HealthTransition(
                from_state=self._state,
                to_state=CameraHealthState.ONLINE,
                reason=REASON_FRAME_RECEIVED,
                timestamp=frame_at,
            )
            self._state = CameraHealthState.ONLINE
        self._log_transition(transition)
        return transition

    def poll(self, now: float | None = None) -> HealthTransition | None:
        """Evaluate silence at ``now`` (defaults to ``clock()``).

        Silence ``> offline_after`` targets ``OFFLINE`` (reason
        silence-offline); elif silence ``> degraded_after`` targets
        ``DEGRADED`` (reason silence-degraded); otherwise no change.
        Exact-equality with either threshold stays. A transition is
        returned (and logged) ONLY when the target differs from the
        current state — this method never recovers towards ``ONLINE``;
        only :meth:`notify_frame` does.

        Raises:
            ValueError: if ``now`` is non-finite or negative.
        """
        current = self._check_timestamp(self._clock() if now is None else now, "now")
        with self._lock:
            reference = self._last_frame_at if self._last_frame_at is not None else self._created_at
            silence = current - reference
            if silence > self._offline_after:
                target = CameraHealthState.OFFLINE
                reason = REASON_SILENCE_OFFLINE
            elif silence > self._degraded_after:
                target = CameraHealthState.DEGRADED
                reason = REASON_SILENCE_DEGRADED
            else:
                return None
            if target is self._state:
                return None
            transition = HealthTransition(
                from_state=self._state,
                to_state=target,
                reason=reason,
                timestamp=current,
            )
            self._state = target
        self._log_transition(transition)
        return transition

    def _log_transition(self, transition: HealthTransition) -> None:
        """Emit one INFO record for an actual transition (never under the lock)."""
        self._logger.info(
            "health transition %s->%s (%s)",
            transition.from_state.value,
            transition.to_state.value,
            transition.reason,
            extra={
                "event": EVENT_TRANSITION,
                "from_state": transition.from_state.value,
                "to_state": transition.to_state.value,
                "reason": transition.reason,
            },
        )

    @property
    def state(self) -> CameraHealthState:
        """Current health state."""
        with self._lock:
            return self._state

    @property
    def last_frame_at(self) -> float | None:
        """Timestamp of the newest accepted frame, or ``None`` if none yet."""
        with self._lock:
            return self._last_frame_at

    def silence(self, now: float | None = None) -> float | None:
        """Seconds since the last frame (or since creation when none yet).

        ``now=None`` reads the injected clock. Always a float in practice
        (the since-creation fallback is defined from construction); the
        ``None`` arm of the return type is retained for signature
        compatibility with the brief.
        """
        current = self._check_timestamp(self._clock() if now is None else now, "now")
        with self._lock:
            reference = self._last_frame_at if self._last_frame_at is not None else self._created_at
            return current - reference

    def __repr__(self) -> str:
        # URL-free by construction: only scalar identity/state/silence.
        with self._lock:
            camera_id = self._camera_id
            state = self._state
            reference = self._last_frame_at if self._last_frame_at is not None else self._created_at
        silence = self._clock() - reference
        return (
            f"StreamHealthMonitor(camera_id={camera_id!r}, "
            f"state={state.value!r}, silence={silence:.3f}s)"
        )


__all__ = [
    "EVENT_TRANSITION",
    "REASON_FRAME_RECEIVED",
    "REASON_SILENCE_DEGRADED",
    "REASON_SILENCE_OFFLINE",
    "CameraHealthState",
    "HealthTransition",
    "StreamHealthMonitor",
]
