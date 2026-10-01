"""Unit tests for StreamHealthMonitor (P1-004).

TDD RED-first suite covering the twelve brief areas. Fake clock ONLY —
zero real sleeps (no ``time.sleep`` anywhere in this file); every timestamp
is injected explicitly or driven by ``FakeClock``.

Area map (brief §Tests):
  1. initial state UNKNOWN, no transition at construction
  2. first frame -> ONLINE + transition
  3. repeated frames stay ONLINE with None (no duplicates)
  4. exact boundaries (strict-greater both sides, both thresholds)
  5. UNKNOWN->DEGRADED->OFFLINE with no frames ever (since-creation silence)
  6. recovery DEGRADED->ONLINE and OFFLINE->ONLINE on frame
  7. no-duplicate polls
  8. invalid timestamps + out-of-order ignore
  9. bad thresholds
  10. fake-clock determinism (exact transition sequence)
  11. logging discipline (transitions log once; silent polls log nothing)
  12. thread smoke (concurrent notify + poll, no sleeps)
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError

import pytest

# RED: this import fails until health.py exists.
from eldercare.vision.stream.health import (
    REASON_FRAME_RECEIVED,
    REASON_SILENCE_DEGRADED,
    REASON_SILENCE_OFFLINE,
    CameraHealthState,
    HealthTransition,
    StreamHealthMonitor,
)


class FakeClock:
    """Deterministic injectable clock (no real time)."""

    def __init__(self, start: float = 0.0) -> None:
        self.now: float = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> float:
        self.now += dt
        return self.now


def _make(clock_start: float = 0.0, **kwargs: object) -> tuple[StreamHealthMonitor, FakeClock]:
    clock = FakeClock(clock_start)
    monitor = StreamHealthMonitor(camera_id="cam-01", clock=clock, **kwargs)  # type: ignore[arg-type]
    return monitor, clock


# --- 0. enum / dataclass contract ---------------------------------------------


def test_states_exact_with_lowercase_values() -> None:
    assert {s.name for s in CameraHealthState} == {"UNKNOWN", "ONLINE", "DEGRADED", "OFFLINE"}
    assert CameraHealthState.UNKNOWN.value == "unknown"
    assert CameraHealthState.ONLINE.value == "online"
    assert CameraHealthState.DEGRADED.value == "degraded"
    assert CameraHealthState.OFFLINE.value == "offline"
    assert CameraHealthState.ONLINE == "online"  # str-enum JSON compatibility
    assert CameraHealthState("offline") is CameraHealthState.OFFLINE


def test_health_transition_is_frozen() -> None:
    transition = HealthTransition(
        from_state=CameraHealthState.UNKNOWN,
        to_state=CameraHealthState.ONLINE,
        reason=REASON_FRAME_RECEIVED,
        timestamp=1.0,
    )
    with pytest.raises(FrozenInstanceError):  # frozen dataclass rejects mutation
        transition.reason = "tampered"  # type: ignore[misc]
    assert transition.reason == REASON_FRAME_RECEIVED


def test_reason_constants_are_distinct_strings() -> None:
    assert isinstance(REASON_FRAME_RECEIVED, str)
    assert isinstance(REASON_SILENCE_DEGRADED, str)
    assert isinstance(REASON_SILENCE_OFFLINE, str)
    assert len({REASON_FRAME_RECEIVED, REASON_SILENCE_DEGRADED, REASON_SILENCE_OFFLINE}) == 3


# --- 1. initial state ----------------------------------------------------------


def test_1_initial_state_unknown_no_transition() -> None:
    monitor, _ = _make()
    assert monitor.state is CameraHealthState.UNKNOWN
    assert monitor.last_frame_at is None
    assert monitor.silence() == pytest.approx(0.0)


# --- 2. first frame ------------------------------------------------------------


def test_2_first_frame_goes_online_with_transition() -> None:
    monitor, _ = _make()
    transition = monitor.notify_frame(10.0)
    assert transition is not None
    assert transition.from_state is CameraHealthState.UNKNOWN
    assert transition.to_state is CameraHealthState.ONLINE
    assert transition.reason == REASON_FRAME_RECEIVED
    assert transition.timestamp == pytest.approx(10.0)
    assert monitor.state is CameraHealthState.ONLINE
    assert monitor.last_frame_at == pytest.approx(10.0)


# --- 3. repeated frames --------------------------------------------------------


def test_3_repeated_frames_stay_online_no_duplicates() -> None:
    monitor, _ = _make()
    assert monitor.notify_frame(1.0) is not None  # UNKNOWN -> ONLINE
    for ts in (2.0, 3.0, 4.0):
        assert monitor.notify_frame(ts) is None
    assert monitor.state is CameraHealthState.ONLINE
    assert monitor.last_frame_at == pytest.approx(4.0)


# --- 4. exact boundaries -------------------------------------------------------


def test_4a_degraded_boundary_strict_greater() -> None:
    monitor, _ = _make()  # degraded_after=2.0, offline_after=10.0
    monitor.notify_frame(0.0)
    assert monitor.poll(2.0) is None  # silence == threshold -> stays ONLINE
    assert monitor.state is CameraHealthState.ONLINE
    transition = monitor.poll(2.0 + 1e-6)  # just over -> DEGRADED
    assert transition is not None
    assert transition.from_state is CameraHealthState.ONLINE
    assert transition.to_state is CameraHealthState.DEGRADED
    assert transition.reason == REASON_SILENCE_DEGRADED
    assert monitor.state is CameraHealthState.DEGRADED


def test_4b_offline_boundary_strict_greater_from_degraded() -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    assert monitor.poll(5.0) is not None  # ONLINE -> DEGRADED
    assert monitor.poll(10.0) is None  # silence == offline_after -> stays DEGRADED
    assert monitor.state is CameraHealthState.DEGRADED
    transition = monitor.poll(10.0 + 1e-6)  # just over -> OFFLINE
    assert transition is not None
    assert transition.from_state is CameraHealthState.DEGRADED
    assert transition.to_state is CameraHealthState.OFFLINE
    assert transition.reason == REASON_SILENCE_OFFLINE
    assert monitor.state is CameraHealthState.OFFLINE


def test_4c_online_jumps_directly_to_offline_on_deep_silence() -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    transition = monitor.poll(100.0)
    assert transition is not None
    assert transition.from_state is CameraHealthState.ONLINE
    assert transition.to_state is CameraHealthState.OFFLINE
    assert transition.reason == REASON_SILENCE_OFFLINE


# --- 5. pre-first-frame progression --------------------------------------------


def test_5_unknown_degrades_then_offlines_with_no_frames() -> None:
    monitor, clock = _make(clock_start=100.0)  # created_at == 100.0
    assert monitor.poll(100.0 + 2.0) is None  # == degraded_after -> stays UNKNOWN
    assert monitor.state is CameraHealthState.UNKNOWN
    first = monitor.poll(100.0 + 2.0 + 1e-6)
    assert first is not None
    assert (first.from_state, first.to_state) == (
        CameraHealthState.UNKNOWN,
        CameraHealthState.DEGRADED,
    )
    assert first.reason == REASON_SILENCE_DEGRADED
    assert monitor.poll(100.0 + 10.0) is None  # == offline_after -> stays DEGRADED
    second = monitor.poll(100.0 + 10.0 + 1e-6)
    assert second is not None
    assert (second.from_state, second.to_state) == (
        CameraHealthState.DEGRADED,
        CameraHealthState.OFFLINE,
    )
    assert second.reason == REASON_SILENCE_OFFLINE
    assert clock() == pytest.approx(100.0)  # explicit timestamps; clock untouched


def test_5b_silence_measures_since_creation_before_first_frame() -> None:
    monitor, clock = _make(clock_start=7.0)
    assert monitor.silence() == pytest.approx(0.0)
    clock.advance(3.0)
    assert monitor.silence() == pytest.approx(3.0)
    assert monitor.silence(9.0) == pytest.approx(2.0)


# --- 6. recovery ----------------------------------------------------------------


def test_6a_degraded_recovers_to_online_on_frame() -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    monitor.poll(5.0)  # -> DEGRADED
    transition = monitor.notify_frame(6.0)
    assert transition is not None
    assert (transition.from_state, transition.to_state) == (
        CameraHealthState.DEGRADED,
        CameraHealthState.ONLINE,
    )
    assert transition.reason == REASON_FRAME_RECEIVED
    assert monitor.state is CameraHealthState.ONLINE


def test_6b_offline_recovers_to_online_on_frame() -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    monitor.poll(50.0)  # -> OFFLINE
    assert monitor.state is CameraHealthState.OFFLINE
    transition = monitor.notify_frame(51.0)
    assert transition is not None
    assert (transition.from_state, transition.to_state) == (
        CameraHealthState.OFFLINE,
        CameraHealthState.ONLINE,
    )
    assert transition.reason == REASON_FRAME_RECEIVED
    assert monitor.state is CameraHealthState.ONLINE


# --- 7. no-duplicate polls -------------------------------------------------------


def test_7_repeated_polls_in_same_state_return_none() -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    assert monitor.poll(5.0) is not None  # ONLINE -> DEGRADED (single emission)
    for _ in range(5):
        assert monitor.poll(5.5) is None
        assert monitor.poll(9.9) is None
    assert monitor.poll(50.0) is not None  # DEGRADED -> OFFLINE (single emission)
    for _ in range(5):
        assert monitor.poll(60.0) is None
    assert monitor.state is CameraHealthState.OFFLINE


# --- 8. invalid + out-of-order timestamps -----------------------------------------


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0, -0.5])
def test_8a_notify_frame_rejects_nonfinite_or_negative(bad: float) -> None:
    monitor, _ = _make()
    with pytest.raises(ValueError):
        monitor.notify_frame(bad)
    assert monitor.state is CameraHealthState.UNKNOWN
    assert monitor.last_frame_at is None


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0])
def test_8b_poll_rejects_nonfinite_or_negative(bad: float) -> None:
    monitor, _ = _make()
    monitor.notify_frame(5.0)
    with pytest.raises(ValueError):
        monitor.poll(bad)
    assert monitor.state is CameraHealthState.ONLINE  # rejected poll changes nothing


def test_8c_out_of_order_frame_ignored() -> None:
    monitor, _ = _make()
    monitor.notify_frame(10.0)
    assert monitor.notify_frame(9.999) is None  # older -> ignored
    assert monitor.state is CameraHealthState.ONLINE
    assert monitor.last_frame_at == pytest.approx(10.0)


def test_8d_out_of_order_frame_ignored_while_degraded() -> None:
    monitor, _ = _make()
    monitor.notify_frame(10.0)
    monitor.poll(15.0)  # -> DEGRADED
    assert monitor.notify_frame(9.0) is None  # older -> ignored, stays DEGRADED
    assert monitor.state is CameraHealthState.DEGRADED
    assert monitor.last_frame_at == pytest.approx(10.0)


def test_8e_equal_timestamp_is_not_out_of_order() -> None:
    monitor, _ = _make()
    monitor.notify_frame(10.0)
    assert monitor.notify_frame(10.0) is None  # equal: accepted, no duplicate
    assert monitor.last_frame_at == pytest.approx(10.0)


# --- 9. bad thresholds -------------------------------------------------------------


@pytest.mark.parametrize(
    "degraded_after,offline_after",
    [
        (10.0, 2.0),  # degraded > offline
        (5.0, 5.0),  # degraded == offline
        (0.0, 10.0),  # degraded zero
        (-1.0, 10.0),  # degraded negative
        (2.0, 0.0),  # offline zero
        (2.0, -3.0),  # offline negative
        (2.0, 2.0),  # equal at defaults-adjacent values
    ],
)
def test_9_bad_thresholds_rejected_naming_relation(
    degraded_after: float, offline_after: float
) -> None:
    with pytest.raises(ValueError, match="degraded_after|offline_after"):
        StreamHealthMonitor(
            camera_id="cam-01",
            degraded_after=degraded_after,
            offline_after=offline_after,
            clock=FakeClock(),
        )


def test_9b_empty_camera_id_rejected() -> None:
    with pytest.raises(ValueError, match="camera_id"):
        StreamHealthMonitor(camera_id="", clock=FakeClock())


def test_9c_default_thresholds_are_brief_values() -> None:
    # Defaults pinned behaviorally (no threshold getters on the monitor):
    # degraded_after=2.0, offline_after=10.0.
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    assert monitor.poll(2.0) is None  # == default degraded_after -> stays ONLINE
    assert monitor.poll(2.0 + 1e-6) is not None  # just over -> DEGRADED
    assert monitor.poll(10.0) is None  # == default offline_after -> stays DEGRADED
    assert monitor.poll(10.0 + 1e-6) is not None  # just over -> OFFLINE


# --- 10. fake-clock determinism -------------------------------------------------------


def test_10_scripted_sequence_produces_exact_transitions() -> None:
    monitor, _ = _make(clock_start=0.0)
    observed: list[HealthTransition | None] = [
        monitor.notify_frame(0.0),  # UNKNOWN -> ONLINE
        monitor.poll(2.0),  # == degraded_after -> None
        monitor.poll(2.0 + 1e-6),  # -> DEGRADED
        monitor.poll(10.0),  # == offline_after -> None
        monitor.poll(10.0 + 1e-6),  # -> OFFLINE
        monitor.notify_frame(10.5),  # -> ONLINE
        monitor.notify_frame(10.5),  # duplicate -> None
    ]
    expected: list[HealthTransition | None] = [
        HealthTransition(
            CameraHealthState.UNKNOWN,
            CameraHealthState.ONLINE,
            REASON_FRAME_RECEIVED,
            0.0,
        ),
        None,
        HealthTransition(
            CameraHealthState.ONLINE,
            CameraHealthState.DEGRADED,
            REASON_SILENCE_DEGRADED,
            2.0 + 1e-6,
        ),
        None,
        HealthTransition(
            CameraHealthState.DEGRADED,
            CameraHealthState.OFFLINE,
            REASON_SILENCE_OFFLINE,
            10.0 + 1e-6,
        ),
        HealthTransition(
            CameraHealthState.OFFLINE, CameraHealthState.ONLINE, REASON_FRAME_RECEIVED, 10.5
        ),
        None,
    ]
    assert observed == expected


# --- 11. logging discipline ---------------------------------------------------------------


@pytest.fixture
def log_records() -> Iterator[list[logging.LogRecord]]:
    """Capture records on the shared ``eldercare`` logger (restores level after)."""
    logger = logging.getLogger("eldercare")
    saved_level = logger.level
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(saved_level)


def _transitions(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, "event", "") == "stream.health.transition"]


def test_11_transitions_log_once_each_silent_polls_log_nothing(
    log_records: list[logging.LogRecord],
) -> None:
    monitor, _ = _make()
    assert _transitions(log_records) == []  # construction logs nothing
    monitor.notify_frame(0.0)  # UNKNOWN -> ONLINE
    monitor.poll(1.0)  # silent
    monitor.poll(1.5)  # silent
    monitor.poll(5.0)  # ONLINE -> DEGRADED
    monitor.poll(6.0)  # silent duplicate
    monitor.poll(60.0)  # DEGRADED -> OFFLINE
    logged = _transitions(log_records)
    assert len(logged) == 3
    assert [(r.from_state, r.to_state) for r in logged] == [  # type: ignore[attr-defined]
        ("unknown", "online"),
        ("online", "degraded"),
        ("degraded", "offline"),
    ]
    reasons = [r.reason for r in logged]  # type: ignore[attr-defined]
    assert reasons == [REASON_FRAME_RECEIVED, REASON_SILENCE_DEGRADED, REASON_SILENCE_OFFLINE]
    assert all(r.levelno == logging.INFO for r in logged)
    assert all(getattr(r, "camera_id", None) == "cam-01" for r in logged)


def test_11b_duplicate_frames_and_polls_emit_no_logs(
    log_records: list[logging.LogRecord],
) -> None:
    monitor, _ = _make()
    monitor.notify_frame(0.0)
    assert len(_transitions(log_records)) == 1
    monitor.notify_frame(1.0)
    monitor.notify_frame(2.0)
    monitor.poll(2.0)  # == degraded_after: silent
    monitor.poll(1.0 + 1e-9)  # still ONLINE window: silent
    assert len(_transitions(log_records)) == 1


# --- 12. thread smoke -----------------------------------------------------------------


def test_12_concurrent_notify_and_poll_no_exception_legal_end_state() -> None:
    monitor, _ = _make(clock_start=0.0)
    errors: list[BaseException] = []

    def _frames() -> None:
        try:
            for i in range(500):  # strictly increasing: always accepted, never stale
                monitor.notify_frame(float(i))
        except BaseException as exc:  # capture for main-thread assertion
            errors.append(exc)

    def _polls() -> None:
        try:
            for _ in range(500):
                monitor.poll(250.0)
        except BaseException as exc:  # capture for main-thread assertion
            errors.append(exc)

    threads = [threading.Thread(target=_frames), threading.Thread(target=_polls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "health monitor thread deadlocked"
    assert not errors
    assert monitor.state in (
        CameraHealthState.ONLINE,
        CameraHealthState.DEGRADED,
        CameraHealthState.OFFLINE,
    )
    # Deterministic close-out: deep silence from any state ends OFFLINE.
    monitor.poll(100000.0)
    assert monitor.state is CameraHealthState.OFFLINE


# --- misc: default clock, repr -----------------------------------------------------------


def test_default_clock_needs_no_injection_and_poll_is_quiet() -> None:
    monitor = StreamHealthMonitor(camera_id="cam-default")
    assert monitor.poll() is None  # fresh monitor, ~zero silence
    assert monitor.state is CameraHealthState.UNKNOWN
    silence = monitor.silence()
    assert silence is not None and silence >= 0.0


def test_repr_carries_identity_without_urls() -> None:
    monitor, _ = _make()
    monitor.notify_frame(3.0)
    text = repr(monitor)
    assert "cam-01" in text
    assert "online" in text
    assert "://" not in text
    assert "http" not in text.lower()
    assert "rtsp" not in text.lower()


def test_silence_tracks_last_frame() -> None:
    monitor, _ = _make()
    monitor.notify_frame(10.0)
    assert monitor.silence(12.5) == pytest.approx(2.5)


def test_clock_factory_type() -> None:
    clock: Callable[[], float] = FakeClock(1.0)
    monitor = StreamHealthMonitor(camera_id="cam-typed", clock=clock)
    assert monitor.silence() == pytest.approx(0.0)
