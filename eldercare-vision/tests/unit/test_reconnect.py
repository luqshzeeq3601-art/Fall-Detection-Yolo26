"""Unit tests for reconnect/backoff core (P1-005).

TDD RED-first suite covering the ten brief areas. Fake sleep (records
calls, never sleeps) + fake clock + scripted capture fakes throughout —
ZERO real sleeps (no ``time.sleep`` anywhere in this file). Every
credential value below is a dummy placeholder used in-process only;
nothing is written to disk.

Area map (brief §Tests):
  1. default policy sequence exact incl. cap flattening
  2. custom policy values + invalid policies / invalid attempt numbers
  3. ``attempt()`` success first-try (no sleep, counters zeroed)
  4. repeated failures via ``connect_with_retry`` (exact sleep sequence)
  5. recovery/reset (fail,fail,success) + renewed failure restarts at base
  6. factory-raises-every-time → handled ``False`` path (real RtspCapture)
  7. cancellation (pre-stopped, mid-sequence, idempotent stop)
  8. recovery emits no fake health transition (real StreamHealthMonitor)
  9. credential safety (last_error / logs / repr are password-free)
  10. no-busy-loop (every sleep arg ``>= base_delay``, count == failures)
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from eldercare.common.logger import JsonFormatter, configure_logging
from eldercare.vision.stream.camera import CameraConfig
from eldercare.vision.stream.capture import RtspCapture
from eldercare.vision.stream.health import (
    REASON_FRAME_RECEIVED,
    REASON_SILENCE_DEGRADED,
    REASON_SILENCE_OFFLINE,
    CameraHealthState,
    StreamHealthMonitor,
)
from eldercare.vision.stream.reconnect import (
    EVENT_ATTEMPT,
    EVENT_GAVE_UP,
    EVENT_RECOVERED,
    EVENT_STOPPED,
    ReconnectController,
    ReconnectPolicy,
)

_RTSP_PLAIN = "rtsp://camera01.local:554/stream1"
_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_RTSP_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"


def _assert_no_raw_secrets(blob: str) -> None:
    assert _DUMMY_USER not in blob
    assert _DUMMY_PASS not in blob


class FakeClock:
    """Deterministic injectable clock (no real time)."""

    def __init__(self, start: float = 0.0) -> None:
        self.now: float = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> float:
        self.now += dt
        return self.now


class FakeSleep:
    """Recording sleep double: stores each requested delay, never sleeps."""

    def __init__(self) -> None:
        self.calls: list[float] = []
        self.hook: Callable[[float], None] | None = None

    def __call__(self, delay: float) -> None:
        self.calls.append(delay)
        if self.hook is not None:
            self.hook(delay)


class FakeCapture:
    """Scripted ``open()`` double; repeats the last result when exhausted."""

    def __init__(self, script: list[bool]) -> None:
        if not script:
            raise ValueError("script must be a non-empty list of open() results")
        self._script: list[bool] = list(script)
        self.open_calls: int = 0
        self.last_error: str | None = None

    def open(self) -> bool:
        self.open_calls += 1
        index = min(self.open_calls - 1, len(self._script) - 1)
        result = self._script[index]
        self.last_error = None if result else "fake open failed"
        return result


def _make_config(url: str = _RTSP_PLAIN, camera_id: str = "cam-01") -> CameraConfig:
    return CameraConfig(camera_id=camera_id, name="Lobby", rtsp_url=url)


def _make(
    script: list[bool],
    policy: ReconnectPolicy | None = None,
) -> tuple[ReconnectController, FakeCapture, FakeSleep, FakeClock]:
    """Build a controller wired to fakes (sleep records, clock is fake)."""
    capture = FakeCapture(script)
    sleep = FakeSleep()
    clock = FakeClock()
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    controller = ReconnectController(
        _make_config(), capture, health, policy=policy, sleep=sleep, clock=clock
    )
    return controller, capture, sleep, clock


@pytest.fixture()
def log_stream() -> Iterator[io.StringIO]:
    """Capture ``eldercare`` JSON log lines (mirrors P1-001/P1-002 style)."""
    logger = logging.getLogger("eldercare")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    configure_logging("INFO")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        handler.close()
        for saved in saved_handlers:
            logger.addHandler(saved)
        logger.setLevel(saved_level)


def _log_records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


# --- Area 1: default policy sequence exact ------------------------------------


def test_1_default_delay_sequence_exact_with_cap_flattening() -> None:
    policy = ReconnectPolicy()
    assert [policy.delay_for(n) for n in range(1, 9)] == [
        1.0,
        2.0,
        4.0,
        8.0,
        16.0,
        30.0,
        30.0,
        30.0,
    ]


# --- Area 2: custom + invalid policies ----------------------------------------


def test_2a_custom_policy_sequence() -> None:
    policy = ReconnectPolicy(base_delay=0.5, multiplier=3.0, max_delay=10.0, max_attempts=4)
    assert [policy.delay_for(n) for n in range(1, 7)] == [0.5, 1.5, 4.5, 10.0, 10.0, 10.0]
    assert policy.max_attempts == 4


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"base_delay": 0.0}, "base_delay"),
        ({"base_delay": -1.0}, "base_delay"),
        ({"multiplier": 0.5}, "multiplier"),
        ({"multiplier": 0.0}, "multiplier"),
        ({"max_delay": 0.5}, "max_delay"),  # below default base_delay=1.0
        ({"base_delay": 5.0, "max_delay": 4.0}, "max_delay"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"max_attempts": -3}, "max_attempts"),
    ],
)
def test_2b_invalid_policies_rejected(kwargs: dict[str, object], fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        ReconnectPolicy(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("attempt", [0, -1, -100])
def test_2c_delay_for_rejects_attempt_below_one(attempt: int) -> None:
    with pytest.raises(ValueError, match="attempt"):
        ReconnectPolicy().delay_for(attempt)


def test_2d_policy_is_frozen() -> None:
    policy = ReconnectPolicy()
    with pytest.raises(FrozenInstanceError):
        policy.base_delay = 5.0  # type: ignore[misc]


def test_2e_huge_attempt_returns_max_delay_without_overflow() -> None:
    assert ReconnectPolicy().delay_for(10**9) == 30.0


# --- Area 3: success first-try -------------------------------------------------


def test_3_attempt_success_first_try_no_sleep(log_stream: io.StringIO) -> None:
    controller, capture, sleep, _ = _make([True])
    assert controller.attempt() is True
    assert capture.open_calls == 1
    assert sleep.calls == []
    assert controller.attempts == 0
    assert controller.consecutive_failures == 0
    assert controller.last_delay is None
    events = [record.get("event") for record in _log_records(log_stream)]
    assert EVENT_RECOVERED in events


# --- Area 4: repeated failures, exact sleep sequence ---------------------------


def test_4_repeated_failures_exact_sleep_sequence(log_stream: io.StringIO) -> None:
    controller, capture, sleep, _ = _make([False])
    assert controller.connect_with_retry(max_attempts=3) is False
    assert capture.open_calls == 3
    assert sleep.calls == [1.0, 2.0, 4.0]
    assert controller.attempts == 3
    assert controller.consecutive_failures == 3
    assert controller.last_delay == 4.0
    events = [record.get("event") for record in _log_records(log_stream)]
    assert events.count(EVENT_ATTEMPT) == 3
    assert EVENT_GAVE_UP in events


# --- Area 5: recovery/reset ----------------------------------------------------


def test_5_recovery_resets_counters_and_restarts_at_base() -> None:
    controller, capture, sleep, _ = _make([False, False, True, False])
    assert controller.attempt() is False  # sleep 1.0
    assert controller.attempt() is False  # sleep 2.0
    assert controller.attempt() is True  # recovery: reset, no sleep
    assert controller.attempts == 0
    assert controller.consecutive_failures == 0
    assert controller.last_delay is None
    assert sleep.calls == [1.0, 2.0]
    assert controller.attempt() is False  # renewed failure restarts at base
    assert sleep.calls == [1.0, 2.0, 1.0]
    assert controller.attempts == 1
    assert controller.consecutive_failures == 1
    assert controller.last_delay == 1.0
    assert capture.open_calls == 4


def test_5b_connect_with_retry_success_after_failures() -> None:
    controller, capture, sleep, _ = _make([False, True])
    assert controller.connect_with_retry(max_attempts_override=5) is True
    assert capture.open_calls == 2
    assert sleep.calls == [1.0]
    assert controller.attempts == 0
    assert controller.consecutive_failures == 0
    assert controller.last_delay is None


# --- Area 6: factory-raises-every-time (real RtspCapture) -----------------------


def test_6_factory_raises_every_time_handled_without_throw() -> None:
    config = _make_config()

    def _raising_factory(url: str) -> Any:
        raise RuntimeError(f"dial failed for {url} token={_DUMMY_PASS}")

    capture = RtspCapture(config, capture_factory=_raising_factory)
    sleep = FakeSleep()
    clock = FakeClock()
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    controller = ReconnectController(config, capture, health, sleep=sleep, clock=clock)
    assert controller.connect_with_retry(max_attempts_override=3) is False
    assert sleep.calls == [1.0, 2.0, 4.0]
    assert controller.attempts == 3
    assert controller.last_delay == 4.0
    assert capture.last_error is not None
    _assert_no_raw_secrets(capture.last_error)


# --- Area 7: cancellation -------------------------------------------------------


def test_7a_prestopped_attempt_does_nothing() -> None:
    controller, capture, sleep, _ = _make([False])
    controller.stop()
    assert controller.stopped is True
    assert controller.attempt() is False
    assert capture.open_calls == 0
    assert sleep.calls == []
    assert controller.connect_with_retry(max_attempts_override=3) is False
    assert capture.open_calls == 0
    assert sleep.calls == []


def test_7b_stop_mid_sequence_exits_promptly() -> None:
    controller, capture, sleep, _ = _make([False] * 10)
    sleep.hook = lambda _delay: controller.stop()
    assert controller.connect_with_retry() is False
    assert controller.stopped is True
    assert capture.open_calls == 1  # no further capture calls after stop
    assert sleep.calls == [1.0]  # no further sleeps after stop
    assert controller.attempts == 1


def test_7c_stop_is_idempotent_with_single_log(log_stream: io.StringIO) -> None:
    controller, _, _, _ = _make([True])
    assert controller.stopped is False
    controller.stop()
    controller.stop()
    controller.stop()
    assert controller.stopped is True
    events = [record.get("event") for record in _log_records(log_stream)]
    assert events.count(EVENT_STOPPED) == 1


# --- Area 8: recovery emits no fake health transition ---------------------------


def test_8_recovery_emits_no_fake_health_transition() -> None:
    clock = FakeClock()
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    capture = FakeCapture([True])
    controller = ReconnectController(
        _make_config(), capture, health, sleep=FakeSleep(), clock=clock
    )
    clock.advance(3.0)
    first = health.poll()
    clock.advance(9.0)  # silence now 12.0 > offline_after
    second = health.poll()
    assert first is not None and second is not None
    assert health.state is CameraHealthState.OFFLINE

    assert controller.attempt() is True  # open success must NOT touch health
    assert health.state is CameraHealthState.OFFLINE
    assert health.last_frame_at is None
    assert health.poll(12.0) is None  # no duplicate emission

    recovered = health.notify_frame(12.0)  # first real frame recovers exactly once
    assert recovered is not None
    assert health.state is CameraHealthState.ONLINE
    assert health.notify_frame(12.5) is None  # already ONLINE: no dup noise

    assert [(t.from_state, t.to_state, t.reason) for t in (first, second, recovered)] == [
        (CameraHealthState.UNKNOWN, CameraHealthState.DEGRADED, REASON_SILENCE_DEGRADED),
        (CameraHealthState.DEGRADED, CameraHealthState.OFFLINE, REASON_SILENCE_OFFLINE),
        (CameraHealthState.OFFLINE, CameraHealthState.ONLINE, REASON_FRAME_RECEIVED),
    ]


# --- Area 9: credential safety ----------------------------------------------------


def test_9_credential_safety_across_error_logs_repr(log_stream: io.StringIO) -> None:
    config = _make_config(url=_RTSP_CREDS)

    def _leaky_factory(url: str) -> Any:
        raise RuntimeError(f"dial failed for {url} token={_DUMMY_PASS}")

    capture = RtspCapture(config, capture_factory=_leaky_factory)
    controller = ReconnectController(
        config,
        capture,
        StreamHealthMonitor(camera_id="cam-01", clock=FakeClock()),
        sleep=FakeSleep(),
        clock=FakeClock(),
    )
    assert controller.attempt() is False
    assert capture.last_error is not None
    _assert_no_raw_secrets(capture.last_error)
    _assert_no_raw_secrets(log_stream.getvalue())
    _assert_no_raw_secrets(repr(controller))
    assert "rtsp://" not in repr(controller)


# --- Area 10: no busy-loop ----------------------------------------------------------


def test_10_no_busy_loop_every_failure_sleeps_at_least_base() -> None:
    policy = ReconnectPolicy()
    controller, _, sleep, _ = _make([False], policy=policy)
    assert controller.connect_with_retry(max_attempts_override=5) is False
    assert sleep.calls == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert len(sleep.calls) == controller.attempts == 5
    assert all(delay >= policy.base_delay for delay in sleep.calls)


def test_10b_no_busy_loop_custom_base() -> None:
    policy = ReconnectPolicy(base_delay=0.25, multiplier=2.0, max_delay=10.0)
    controller, _, sleep, _ = _make([False], policy=policy)
    assert controller.connect_with_retry(max_attempts_override=4) is False
    assert sleep.calls == [0.25, 0.5, 1.0, 2.0]
    assert all(delay >= policy.base_delay for delay in sleep.calls)


# --- Contract extras: repr, overrides, validation ------------------------------------


def test_repr_carries_ids_and_counts_without_url() -> None:
    controller, _, _, _ = _make([False])
    assert controller.attempt() is False
    text = repr(controller)
    assert "cam-01" in text
    assert "attempts=1" in text
    assert "consecutive_failures=1" in text
    assert "stopped=False" in text
    assert "rtsp://" not in text
    assert "camera01.local" not in text


def test_invalid_override_rejected() -> None:
    controller, _, _, _ = _make([False])
    with pytest.raises(ValueError, match="max_attempts_override"):
        controller.connect_with_retry(max_attempts_override=0)


def test_conflicting_overrides_rejected() -> None:
    controller, _, _, _ = _make([True])
    with pytest.raises(ValueError, match="max_attempts"):
        controller.connect_with_retry(max_attempts_override=2, max_attempts=3)


def test_matching_overrides_agree() -> None:
    controller, capture, sleep, _ = _make([True])
    assert controller.connect_with_retry(max_attempts_override=2, max_attempts=2) is True
    assert capture.open_calls == 1
    assert sleep.calls == []
