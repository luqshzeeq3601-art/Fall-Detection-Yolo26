"""Integration tests for fall confidence scoring and cooldown behavior in live state machine."""

from __future__ import annotations

from eldercare.fall_engine.confidence.cooldown import (
    CooldownConfig,
    IncidentCooldownManager,
)
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from eldercare.fall_engine.state_machine.machine import (
    FallStateMachineManager,
    TrackFallStateMachine,
)
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from tests.fixtures.synthetic_fall_fixtures import (
    LEFT_ANKLE,
    LEFT_KNEE,
    RIGHT_ANKLE,
    RIGHT_KNEE,
    generate_fall_sequence,
    generate_fall_with_recovery_sequence,
    mask_missing_keypoints,
)


def test_end_to_end_fall_event_contains_explainable_breakdown() -> None:
    """Verify emitted FallEvent contains full explainable evidence breakdown (AC-024)."""
    sm = TrackFallStateMachine(
        camera_id="cam-01",
        track_id=1,
        config=FallStateMachineConfig(down_confirmation_sec=0.8),
    )
    seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)

    emitted_event: FallEvent | None = None
    for i in range(1, len(seq) + 1):
        state, ev = sm.update(seq[:i])
        if ev is not None:
            emitted_event = ev

    assert emitted_event is not None
    assert emitted_event.confidence > 0.6
    assert emitted_event.confidence_breakdown is not None

    bd = emitted_event.confidence_breakdown
    assert bd.composite_confidence == emitted_event.confidence
    assert bd.motion_score > 0.0
    assert bd.posture_score > 0.0
    assert bd.persistence_score > 0.0
    assert bd.detector_model == "yolo26s-pose.pt"
    assert bd.tracker_name == "bytetrack"
    assert bd.config_version == "1.0.0"
    assert "normalized_peak_vertical_velocity" in bd.key_contributing_features
    assert "torso_angle_deg" in bd.key_contributing_features


def test_cooldown_suppresses_rapid_re_alert_storm() -> None:
    """Verify repeated falls within cooldown window suppress duplicate alert emission (AC-025)."""
    cooldown_mgr = IncidentCooldownManager(config=CooldownConfig(incident_cooldown_sec=10.0))
    sm = TrackFallStateMachine(
        camera_id="cam-01",
        track_id=1,
        config=FallStateMachineConfig(down_confirmation_sec=0.5, recovery_cooldown_sec=1.0),
        cooldown_manager=cooldown_mgr,
    )

    # First fall sequence (duration 3.0s, fall start 0.5s)
    seq1 = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    events1: list[FallEvent] = []
    for i in range(1, len(seq1) + 1):
        _, ev = sm.update(seq1[:i])
        if ev is not None:
            events1.append(ev)

    assert len(events1) == 1
    assert sm.state == FallState.FALL_CONFIRMED

    # Person recovers back to NORMAL (e.g. from t=3.0 to t=5.0)
    rec_seq = generate_fall_with_recovery_sequence(
        duration_sec=3.0,
        fps=15.0,
        start_time=3.0,
        fall_start_sec=0.1,
        descent_duration_sec=0.2,
        down_duration_sec=0.3,
        recovery_duration_sec=0.5,
    )
    for i in range(1, len(rec_seq) + 1):
        sm.update(rec_seq[:i])

    # Second fall occurs at t=6.0 (< 10.0s cooldown from first incident at ~1.35s)
    seq2 = generate_fall_sequence(duration_sec=2.0, fps=15.0, start_time=6.0, fall_start_sec=0.2)
    events2: list[FallEvent] = []
    for i in range(1, len(seq2) + 1):
        _, ev = sm.update(seq2[:i])
        if ev is not None:
            events2.append(ev)

    # Second fall is confirmed in state machine, but suppressed from emitting duplicate event
    assert len(events2) == 0
    assert sm.state == FallState.FALL_CONFIRMED


def test_missing_keypoint_fall_generates_event_with_penalized_confidence() -> None:
    """Fall with occluded lower limbs generates FallEvent with lower confidence (AC-026)."""
    sm = TrackFallStateMachine(
        camera_id="cam-01",
        track_id=1,
        config=FallStateMachineConfig(down_confirmation_sec=0.8),
    )
    raw_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    occluded_seq = [
        mask_missing_keypoints(obs, [LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE])
        for obs in raw_seq
    ]

    emitted_event: FallEvent | None = None
    for i in range(1, len(occluded_seq) + 1):
        _, ev = sm.update(occluded_seq[:i])
        if ev is not None:
            emitted_event = ev

    assert emitted_event is not None
    assert emitted_event.confidence_breakdown is not None
    assert emitted_event.confidence_breakdown.missing_keypoint_penalty > 0.0


def test_multi_person_manager_cooldown_isolation() -> None:
    """Manager ensures cooldown on person 1 does not suppress valid alert on person 2."""
    cooldown_mgr = IncidentCooldownManager(
        config=CooldownConfig(incident_cooldown_sec=10.0, camera_cooldown_sec=0.1)
    )
    manager = FallStateMachineManager(
        config=FallStateMachineConfig(down_confirmation_sec=0.8),
        cooldown_manager=cooldown_mgr,
    )

    p1_seq = generate_fall_sequence(
        camera_id="cam-01", track_id=1, duration_sec=3.0, fps=15.0, fall_start_sec=0.5
    )
    p2_seq = generate_fall_sequence(
        camera_id="cam-01", track_id=2, duration_sec=3.0, fps=15.0, fall_start_sec=1.5
    )

    p1_events: list[FallEvent] = []
    p2_events: list[FallEvent] = []

    # Stream both tracks
    for i in range(1, len(p1_seq) + 1):
        _, e1 = manager.update_track("cam-01", 1, p1_seq[:i])
        if e1 is not None:
            p1_events.append(e1)

    for i in range(1, len(p2_seq) + 1):
        _, e2 = manager.update_track("cam-01", 2, p2_seq[:i])
        if e2 is not None:
            p2_events.append(e2)

    assert len(p1_events) == 1
    assert len(p2_events) == 1
    assert p1_events[0].track_id == 1
    assert p2_events[0].track_id == 2
