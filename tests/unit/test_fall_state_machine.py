"""Unit tests for the fall detection state machine and manager."""

from __future__ import annotations

import ast
from pathlib import Path

from eldercare.fall_engine.state_machine import (
    FallEvent,
    FallState,
    FallStateMachineConfig,
    FallStateMachineManager,
    TrackFallStateMachine,
)
from tests.fixtures.synthetic_fall_fixtures import (
    build_track_observation,
    generate_fall_sequence,
    generate_walking_sequence,
    make_fallen_pose,
    make_standing_pose,
)


def test_initial_state_is_normal() -> None:
    """State machine starts in NORMAL state with zero transitions."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    assert sm.state == FallState.NORMAL
    assert sm.confirmed_event is None
    assert len(sm.transitions) == 0


def test_normal_to_descent_candidate_on_rapid_velocity() -> None:
    """Rapid downward velocity triggers transition from NORMAL to DESCENT_CANDIDATE."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    # Standing pose at t=0.0
    obs1 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=300.0, height=300.0), timestamp=0.0
    )
    # Pose dropping rapidly at t=0.1 (downward delta = 200px -> 2000px/s, > 6.0 heights/s)
    obs2 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=500.0, height=300.0), timestamp=0.1
    )

    state, event = sm.update([obs1, obs2])
    assert state == FallState.DESCENT_CANDIDATE
    assert event is None
    assert len(sm.transitions) == 1
    assert sm.transitions[0].to_state == FallState.DESCENT_CANDIDATE


def test_descent_candidate_timeout_returns_to_normal() -> None:
    """If down posture is not reached within timeout, candidate reverts to NORMAL."""
    config = FallStateMachineConfig(descent_candidate_timeout_sec=0.5)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)

    # Initial rapid motion
    obs1 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=300.0, height=300.0), timestamp=0.0
    )
    obs2 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=450.0, height=300.0), timestamp=0.1
    )
    sm.update([obs1, obs2])
    assert sm.state == FallState.DESCENT_CANDIDATE

    # Subsequent observations remain upright, exceeding candidate timeout (0.5s)
    obs3 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=450.0, height=300.0), timestamp=0.7
    )
    state, event = sm.update([obs2, obs3])
    assert state == FallState.NORMAL
    assert event is None


def test_single_down_frame_insufficient_for_down_confirming() -> None:
    """A single low frame while in candidate is not enough when min_down_frames >= 2."""
    config = FallStateMachineConfig(min_down_confirming_frames=2)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)

    # Trigger candidate
    obs1 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=300.0, height=300.0), timestamp=0.0
    )
    obs2 = build_track_observation(
        make_standing_pose(center_x=320.0, base_y=450.0, height=300.0), timestamp=0.1
    )
    sm.update([obs1, obs2])
    assert sm.state == FallState.DESCENT_CANDIDATE

    # First down frame: should still stay in DESCENT_CANDIDATE (down_frame_count = 1)
    obs3 = build_track_observation(make_fallen_pose(center_x=320.0, floor_y=450.0), timestamp=0.2)
    state, event = sm.update([obs2, obs3])
    assert state == FallState.DESCENT_CANDIDATE
    assert event is None

    # Second down frame: should transition to DOWN_CONFIRMING (down_frame_count = 2)
    obs4 = build_track_observation(make_fallen_pose(center_x=320.0, floor_y=450.0), timestamp=0.3)
    state, event = sm.update([obs3, obs4])
    assert state == FallState.DOWN_CONFIRMING
    assert event is None


def test_down_confirming_to_fall_confirmed_on_duration() -> None:
    """Down posture sustained for down_confirmation_sec triggers FALL_CONFIRMED."""
    config = FallStateMachineConfig(min_down_confirming_frames=2, down_confirmation_sec=1.0)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)

    # Fast forward into DOWN_CONFIRMING at t=0.3
    obs_list = [
        build_track_observation(make_standing_pose(base_y=300.0, height=300.0), timestamp=0.0),
        build_track_observation(make_standing_pose(base_y=450.0, height=300.0), timestamp=0.1),
        build_track_observation(make_fallen_pose(floor_y=450.0), timestamp=0.2),
        build_track_observation(make_fallen_pose(floor_y=450.0), timestamp=0.3),
    ]
    for i in range(1, len(obs_list)):
        sm.update(obs_list[: i + 1])
    assert sm.state == FallState.DOWN_CONFIRMING

    # At t=0.8 (0.5s into down confirmation): should still be DOWN_CONFIRMING
    obs_mid = build_track_observation(make_fallen_pose(floor_y=450.0), timestamp=0.8)
    state, event = sm.update([obs_list[-1], obs_mid])
    assert state == FallState.DOWN_CONFIRMING
    assert event is None

    # At t=1.35 (1.05s into down confirmation >= 1.0s): should be FALL_CONFIRMED
    obs_end = build_track_observation(make_fallen_pose(floor_y=450.0), timestamp=1.35)
    state, event = sm.update([obs_mid, obs_end])
    assert state == FallState.FALL_CONFIRMED
    assert isinstance(event, FallEvent)
    assert event.camera_id == "cam-01"
    assert event.track_id == 1
    assert event.confirmed_timestamp == 1.35


def test_fall_confirmed_suppresses_duplicate_alerts() -> None:
    """While in FALL_CONFIRMED, subsequent down observations do not emit new events."""
    config = FallStateMachineConfig(min_down_confirming_frames=1, down_confirmation_sec=0.2)
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)

    obs1 = build_track_observation(make_standing_pose(base_y=300.0), timestamp=0.0)
    obs2 = build_track_observation(make_standing_pose(base_y=480.0), timestamp=0.1)
    obs3 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.2)
    obs4 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.5)

    sm.update([obs1, obs2])
    sm.update([obs2, obs3])
    state, event1 = sm.update([obs3, obs4])
    assert state == FallState.FALL_CONFIRMED
    assert event1 is not None

    # Subsequent down frames
    obs5 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.6)
    obs6 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.7)
    state5, event2 = sm.update([obs4, obs5])
    state6, event3 = sm.update([obs5, obs6])

    assert state5 == FallState.FALL_CONFIRMED
    assert event2 is None
    assert state6 == FallState.FALL_CONFIRMED
    assert event3 is None


def test_fall_confirmed_to_recovery_and_normal() -> None:
    """Standing up after confirmed fall enters RECOVERY and then NORMAL after cooldown."""
    config = FallStateMachineConfig(
        min_down_confirming_frames=1,
        down_confirmation_sec=0.2,
        recovery_cooldown_sec=2.0,
    )
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1, config=config)

    # Reach FALL_CONFIRMED at t=0.8
    obs1 = build_track_observation(make_standing_pose(base_y=300.0), timestamp=0.0)
    obs2 = build_track_observation(make_standing_pose(base_y=480.0), timestamp=0.1)
    obs3 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.5)
    obs4 = build_track_observation(make_fallen_pose(floor_y=480.0), timestamp=0.8)
    sm.update([obs1, obs2])
    sm.update([obs2, obs3])
    sm.update([obs3, obs4])
    assert sm.state == FallState.FALL_CONFIRMED

    # Person stands up at t=1.0 -> RECOVERY
    obs_up = build_track_observation(make_standing_pose(base_y=450.0), timestamp=1.0)
    state, event = sm.update([obs4, obs_up])
    assert state == FallState.RECOVERY
    assert event is None

    # Person stays standing at t=2.0 (1.0s cooldown < 2.0s) -> still RECOVERY
    obs_up2 = build_track_observation(make_standing_pose(base_y=450.0), timestamp=2.0)
    state, _ = sm.update([obs_up, obs_up2])
    assert state == FallState.RECOVERY

    # Person stays standing at t=3.5 (2.5s cooldown >= 2.0s) -> NORMAL
    obs_up3 = build_track_observation(make_standing_pose(base_y=450.0), timestamp=3.5)
    state, _ = sm.update([obs_up2, obs_up3])
    assert state == FallState.NORMAL


def test_manager_multi_track_isolation_and_cleanup() -> None:
    """Manager correctly isolates tracks and cleans up expired tracks."""
    manager = FallStateMachineManager(config=FallStateMachineConfig(down_confirmation_sec=0.5))

    walk_seq = generate_walking_sequence(camera_id="cam-01", track_id=1, duration_sec=1.0)
    fall_seq = generate_fall_sequence(camera_id="cam-01", track_id=2, duration_sec=2.5)

    # Update track 1 with walking
    state1, ev1 = manager.update_track("cam-01", 1, walk_seq)
    assert state1 == FallState.NORMAL
    assert ev1 is None

    # Update track 2 with fall
    for i in range(1, len(fall_seq) + 1):
        manager.update_track("cam-01", 2, fall_seq[:i])

    assert manager.get_state("cam-01", 1) == FallState.NORMAL
    assert manager.get_state("cam-01", 2) == FallState.FALL_CONFIRMED
    assert manager.active_tracks_count == 2

    # Cleanup: track 1 expires, track 2 remains active
    removed = manager.cleanup_expired_tracks({("cam-01", 2)})
    assert removed == 1
    assert manager.active_tracks_count == 1
    assert manager.get_state("cam-01", 1) == FallState.NORMAL  # Default for unknown
    assert manager.get_state("cam-01", 2) == FallState.FALL_CONFIRMED


def test_state_machine_reset() -> None:
    """Reset cleanly wipes internal timestamps and transitions."""
    sm = TrackFallStateMachine(camera_id="cam-01", track_id=1)
    obs1 = build_track_observation(make_standing_pose(base_y=300.0), timestamp=0.0)
    obs2 = build_track_observation(make_standing_pose(base_y=480.0), timestamp=0.1)
    sm.update([obs1, obs2])
    assert len(sm.transitions) > 0

    sm.reset()
    assert sm.state == FallState.NORMAL
    assert len(sm.transitions) == 0
    assert sm.candidate_timestamp is None
    assert sm.down_start_timestamp is None


def test_framework_freedom_ast_scan() -> None:
    """Verify state_machine modules do not import forbidden frameworks."""
    import eldercare.fall_engine.state_machine as sm_pkg
    import eldercare.fall_engine.state_machine.config as config_mod
    import eldercare.fall_engine.state_machine.machine as machine_mod
    import eldercare.fall_engine.state_machine.states as states_mod

    modules = [sm_pkg, states_mod, config_mod, machine_mod]
    forbidden_roots = ["cv2", "torch", "ultralytics", "torchvision"]

    for mod in modules:
        mod_path = Path(mod.__file__)
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        imported_roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.append(node.module.split(".")[0])

        for forbidden in forbidden_roots:
            assert forbidden not in imported_roots, f"Module {mod.__name__} imports {forbidden}"
