"""Bounded exponential reconnect/backoff core (P1-005).

Delay formula (deterministic, NO jitter)::

    delay_for(attempt) = min(base_delay * multiplier ** (attempt - 1), max_delay)

with ``attempt >= 1``. Jitter is deliberately absent: this is a
single-camera local POC where reproducible timing beats thundering-herd
avoidance; adding jitter later is a documented option, not implemented
here (backoff tuning is benchmark-driven work for a later task).

Worked example (defaults: ``base_delay=1.0``, ``multiplier=2.0``,
``max_delay=30.0``): attempts 1..7 yield ``1, 2, 4, 8, 16, 30, 30``
— the raw exponential ``32`` at attempt 6 is flattened by the cap.

Honesty rule
------------
A successful ``capture.open()`` resets the backoff counters but does NOT
touch :class:`~eldercare.vision.stream.health.StreamHealthMonitor`:
open-success is not health-ONLINE. The monitor recovers only on real
frames via ``notify_frame``. This module therefore never manufactures a
health transition.

Stop semantics
--------------
``stop()`` is idempotent and thread-safe: the first call flips the flag
and logs one ``stream.reconnect.stopped`` line; later calls are silent.
``attempt()`` returns ``False`` immediately when stopped (no capture
call, no sleep). ``connect_with_retry`` re-checks the flag every
iteration, so a stop issued from inside the injected sleep (or another
thread) exits promptly with ``False``.

What is NOT here
----------------
MQTT camera events (Phase 7), persistence (Phase 5), FPS/capture
telemetry (P1-006), threads/timers (the caller drives; ``sleep`` is
injected and fake in tests), backoff tuning (benchmark-driven, later).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from eldercare.common.logger import get_logger
from eldercare.common.redaction import sanitize_exception_message
from eldercare.vision.stream.camera import CameraConfig
from eldercare.vision.stream.capture import RtspCapture
from eldercare.vision.stream.health import StreamHealthMonitor

#: Log event for a failed attempt (WARNING, numeric/id fields only).
EVENT_ATTEMPT: str = "stream.reconnect.attempt"

#: Log event for a successful open (INFO).
EVENT_RECOVERED: str = "stream.reconnect.recovered"

#: Log event when an attempt cap is reached (WARNING).
EVENT_GAVE_UP: str = "stream.reconnect.gave_up"

#: Log event for the first ``stop()`` transition (INFO).
EVENT_STOPPED: str = "stream.reconnect.stopped"


def _check_delay(value: float | int, name: str) -> float:
    """Validate a delay parameter; return it as ``float``.

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
class ReconnectPolicy:
    """Bounded exponential backoff parameters (frozen, pure timing).

    Args:
        base_delay: First-retry delay in seconds; must be ``> 0``.
        multiplier: Per-attempt growth factor; must be ``>= 1.0``.
        max_delay: Hard ceiling; must be ``>= base_delay``.
        max_attempts: Total-attempt cap (``None`` = retry until stopped);
            when set must be an ``int >= 1``.

    Raises:
        ValueError: naming the violated relation when any invariant fails.
    """

    base_delay: float = 1.0
    multiplier: float = 2.0
    max_delay: float = 30.0
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        base = _check_delay(self.base_delay, "base_delay")
        mult = _check_delay(self.multiplier, "multiplier")
        ceiling = _check_delay(self.max_delay, "max_delay")
        if not base > 0:
            raise ValueError(f"base_delay must be > 0, got {self.base_delay!r}")
        if not mult >= 1.0:
            raise ValueError(f"multiplier must be >= 1.0, got {self.multiplier!r}")
        if not ceiling >= base:
            raise ValueError(
                "max_delay must be >= base_delay, "
                f"got max_delay={self.max_delay!r}, base_delay={self.base_delay!r}"
            )
        attempts = self.max_attempts
        if attempts is not None and (
            isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1
        ):
            raise ValueError(f"max_attempts must be None or an int >= 1, got {attempts!r}")

    def delay_for(self, attempt: int) -> float:
        """Return the deterministic delay for 1-based ``attempt``.

        ``min(base_delay * multiplier ** (attempt - 1), max_delay)`` —
        pure (no clock, no sleep, no jitter).

        Raises:
            ValueError: if ``attempt`` is not an ``int >= 1``.
        """
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError(f"attempt must be an int >= 1, got {attempt!r}")
        try:
            raw = self.base_delay * (self.multiplier ** (attempt - 1))
        except OverflowError:
            # Astronomically large attempts overflow the float exponential;
            # the cap dominates there anyway, so return it directly.
            return float(self.max_delay)
        return float(min(raw, self.max_delay))


class ReconnectController:
    """One-attempt reconnect driver with injected sleep/clock.

    Holds DI references (does NOT own or create them — components are
    pre-validated upstream). Threading model: safe to share like
    ``LatestFrameQueue``/``StreamHealthMonitor`` — a single
    ``threading.Lock`` guards all mutable state, and no I/O (logging or
    sleeping) happens inside the lock. The injected ``clock`` is stored
    for signature stability with the health monitor and future manager
    integration; current timing needs no wall-clock reads (delays come
    from the policy).

    Args:
        config: Camera identity (only ``camera_id`` is ever rendered).
        capture: Capture seam; its ``open()`` never raises ``Exception``.
        health: Health monitor (kept for manager wiring; never written
            by this controller — see the honesty rule above).
        policy: Backoff parameters (defaults when ``None``).
        sleep: Delay function (defaults to :func:`time.sleep`); tests
            inject a recording fake so the suite performs zero real
            sleeping.
        clock: Seconds source (defaults to :func:`time.monotonic`).
    """

    def __init__(
        self,
        config: CameraConfig,
        capture: RtspCapture,
        health: StreamHealthMonitor,
        policy: ReconnectPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._capture = capture
        self._health = health
        self._policy = policy if policy is not None else ReconnectPolicy()
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self.attempts: int = 0
        self.consecutive_failures: int = 0
        self.last_delay: float | None = None
        self._stopped: bool = False
        self._logger = get_logger(
            service="vision", component="stream.reconnect", camera_id=config.camera_id
        )

    @property
    def stopped(self) -> bool:
        """Whether :meth:`stop` has been called."""
        with self._lock:
            return self._stopped

    def stop(self) -> None:
        """Request cancellation; idempotent and thread-safe.

        The first call flips the flag and logs one INFO line; later
        calls change nothing and log nothing.
        """
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self._logger.info("reconnect stopped", extra={"event": EVENT_STOPPED})

    def attempt(self) -> bool:
        """Perform ONE open attempt; ``True`` on success, ``False`` otherwise.

        Stopped → ``False`` immediately (no capture call, no sleep).
        Success resets ``attempts``/``consecutive_failures`` to 0 and
        ``last_delay`` to ``None`` (and logs recovery) but never writes
        the health monitor. Failure bumps both counters, records
        ``delay_for(attempts)`` in ``last_delay``, logs the outcome
        (WARNING, attempt/max/delay — camera_id + numbers only, never
        URLs), sleeps exactly that delay, and returns ``False``.
        """
        with self._lock:
            if self._stopped:
                return False
        if self._capture.open():
            with self._lock:
                self.attempts = 0
                self.consecutive_failures = 0
                self.last_delay = None
            self._logger.info("reconnect recovered", extra={"event": EVENT_RECOVERED})
            return True
        with self._lock:
            self.attempts += 1
            self.consecutive_failures += 1
            delay = self._policy.delay_for(self.attempts)
            self.last_delay = delay
            attempt_no = self.attempts
        self._logger.warning(
            "reconnect attempt %d failed; retry in %.3fs",
            attempt_no,
            delay,
            extra={
                "event": EVENT_ATTEMPT,
                "attempt": attempt_no,
                "max_attempts": self._policy.max_attempts,
                "delay": delay,
            },
        )
        self._sleep(delay)
        return False

    def connect_with_retry(
        self,
        max_attempts_override: int | None = None,
        *,
        max_attempts: int | None = None,
    ) -> bool:
        """Loop :meth:`attempt` until success, stop, or the attempt cap.

        The effective cap is ``max_attempts_override ?? max_attempts ??
        policy.max_attempts`` (``None`` = retry until stopped). Both
        keyword spellings are accepted for brief compatibility; when both
        are given they must agree. ``True`` on success, else ``False``.
        The cap bounds iterations of this call only; lifetime ``attempts``
        is cumulative and unaffected by the cap.

        No busy-looping is possible: every failing iteration sleeps
        ``>= base_delay > 0`` before the next attempt.

        Raises:
            ValueError: if an override is not an ``int >= 1``, or the two
                overrides disagree.
        """
        cap = self._resolve_cap(max_attempts_override, max_attempts)
        made = 0
        while True:
            if self.stopped:
                return False
            if cap is not None and made >= cap:
                self._logger.warning(
                    "reconnect gave up after %d attempts (cap %d)",
                    made,
                    cap,
                    extra={"event": EVENT_GAVE_UP, "attempts": made, "max_attempts": cap},
                )
                return False
            if self.attempt():
                return True
            made += 1

    def _resolve_cap(self, override: int | None, alias: int | None) -> int | None:
        """Resolve the effective attempt cap, validating both spellings."""
        for name, value in (("max_attempts_override", override), ("max_attempts", alias)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{name} must be None or an int >= 1, got {value!r}")
        if override is not None and alias is not None and override != alias:
            raise ValueError(
                f"max_attempts_override and max_attempts disagree: {override!r} != {alias!r}"
            )
        if override is not None:
            return override
        if alias is not None:
            return alias
        return self._policy.max_attempts

    def __repr__(self) -> str:
        # URL-free by construction: camera_id + scalar counters only. The
        # held CameraConfig URL is never formatted; camera_id passes through
        # the sanitizer defense-in-depth (it is pattern-validated upstream,
        # and the bound logger sanitizes structurally at format time too).
        with self._lock:
            camera_id = sanitize_exception_message(self._config.camera_id)
            return (
                f"ReconnectController(camera_id={camera_id!r}, "
                f"attempts={self.attempts!r}, "
                f"consecutive_failures={self.consecutive_failures!r}, "
                f"stopped={self._stopped!r})"
            )

    def __str__(self) -> str:
        return self.__repr__()


__all__ = [
    "EVENT_ATTEMPT",
    "EVENT_GAVE_UP",
    "EVENT_RECOVERED",
    "EVENT_STOPPED",
    "ReconnectController",
    "ReconnectPolicy",
]
