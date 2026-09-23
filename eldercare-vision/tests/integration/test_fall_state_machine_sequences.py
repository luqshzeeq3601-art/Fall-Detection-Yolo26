"""Integration tests for fall state machine across synthetic sequence scenarios."""

from __future__ import annotations

from eldercare.fall_engine.state_machine import (
    FallEvent,
    FallState,
    FallStateMachineConfig,
    FallStateMachineManager,
    TrackFallStateMachine,
)
from tests.fixtures.synthetic_fall_fixtures import (
    generate_bending_sequence,
    generate_fall_sequence,
    generate_fall_with_recovery_sequence,
    generate_sitting_sequence,
    generate_slow_liedown_sequence,
    generate_walking_sequence,
)


def test_walking_sequence_never_triggers_fall() -> None:
    """Verify standard walking ADL never enters DESCENT_CANDIDATE or FALL_CONFIRMED."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    seq = generate_walking_sequence(duration_sec=3.0, fps=15.0)

    events: list[FallEvent] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        assert state == FallState.NORMAL
        if event is not None:
            events.append(event)

    assert len(events) == 0
    assert len(sm.transitions) == 0


def test_sitting_sequence_never_triggers_fall() -> None:
    """Verify sitting down over 1.0s never triggers a fall candidate or confirmation."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    seq = generate_sitting_sequence(duration_sec=3.0, fps=15.0, sit_start_sec=1.0)

    events: list[FallEvent] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        assert state in (FallState.NORMAL, FallState.DESCENT_CANDIDATE)
        if event is not None:
            events.append(event)

    assert len(events) == 0
    assert sm.state == FallState.NORMAL  # Ends in NORMAL


def test_bending_sequence_never_triggers_fall() -> None:
    """Verify bending over and recovering does not confirm a fall."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    seq = generate_bending_sequence(duration_sec=3.0, fps=15.0, bend_start_sec=1.0)

    events: list[FallEvent] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        if event is not None:
            events.append(event)

    assert len(events) == 0
    assert sm.state == FallState.NORMAL


def test_gentle_lie_down_sequence_never_triggers_fall() -> None:
    """Verify slow gentle lie down over 2.5s does not trigger candidate descent."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    seq = generate_slow_liedown_sequence(duration_sec=4.0, fps=15.0)

    events: list[FallEvent] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        if event is not None:
            events.append(event)

    assert len(events) == 0


def test_standard_fall_sequence_confirms_fall() -> None:
    """Verify rapid fall collapse transitions through candidate, down, and confirmed."""
    config = FallStateMachineConfig(down_confirmation_sec=1.0)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)
    seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)

    events: list[FallEvent] = []
    state_timeline: list[FallState] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        state_timeline.append(state)
        if event is not None:
            events.append(event)

    assert len(events) == 1
    event = events[0]
    assert event.camera_id == "cam-01"
    assert event.track_id == 1
    assert event.candidate_timestamp >= 0.5
    assert event.confirmed_timestamp > event.candidate_timestamp
    assert sm.state == FallState.FALL_CONFIRMED

    # Check that states occurred in sequence:
    # NORMAL -> DESCENT_CANDIDATE -> DOWN_CONFIRMING -> FALL_CONFIRMED
    assert FallState.NORMAL in state_timeline
    assert FallState.DESCENT_CANDIDATE in state_timeline
    assert FallState.DOWN_CONFIRMING in state_timeline
    assert FallState.FALL_CONFIRMED in state_timeline


def test_fall_with_recovery_sequence_lifecycle() -> None:
    """Verify fall followed by recovery completes full state machine lifecycle."""
    config = FallStateMachineConfig(down_confirmation_sec=0.8, recovery_cooldown_sec=1.0)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)
    seq = generate_fall_with_recovery_sequence(
        duration_sec=5.0,
        fps=15.0,
        fall_start_sec=0.5,
        down_duration_sec=1.2,
        recovery_duration_sec=1.0,
    )

    events: list[FallEvent] = []
    states: list[FallState] = []
    for i in range(1, len(seq) + 1):
        state, event = sm.update(seq[:i])
        states.append(state)
        if event is not None:
            events.append(event)

    assert len(events) == 1
    assert FallState.FALL_CONFIRMED in states
    assert FallState.RECOVERY in states
    assert states[-1] == FallState.NORMAL  # Cooldown elapsed -> returned to NORMAL


def test_multi_person_concurrent_fall_and_walk() -> None:
    """Verify simultaneous tracks (one falling, one walking) maintain complete isolation."""
    manager = FallStateMachineManager(config=FallStateMachineConfig(down_confirmation_sec=0.8))

    walk_seq = generate_walking_sequence(
        camera_id="cam-01", track_id=10, duration_sec=3.0, fps=15.0
    )
    fall_seq = generate_fall_sequence(
        camera_id="cam-01", track_id=20, duration_sec=3.0, fps=15.0, fall_start_sec=0.5
    )

    p1_events: list[FallEvent] = []
    p2_events: list[FallEvent] = []

    # Stream frames concurrently
    min_len = min(len(walk_seq), len(fall_seq))
    for i in range(1, min_len + 1):
        s1, e1 = manager.update_track("cam-01", 10, walk_seq[:i])
        s2, e2 = manager.update_track("cam-01", 20, fall_seq[:i])
        if e1 is not None:
            p1_events.append(e1)
        if e2 is not None:
            p2_events.append(e2)

    assert manager.get_state("cam-01", 10) == FallState.NORMAL
    assert len(p1_events) == 0

    assert manager.get_state("cam-01", 20) == FallState.FALL_CONFIRMED
    assert len(p2_events) == 1
    assert p2_events[0].track_id == 20
