"""Unit tests for the synthetic fall fixtures module (P4-001).

Validates that synthetic fixtures produce valid, deterministic, frozen
domain objects (Keypoint, PersonPose, TrackObservation, TrackHistory)
with physically plausible geometry across all required ADL and fall scenarios.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint, PersonPose
from eldercare.vision.tracking.history import TrackHistory
from eldercare.vision.tracking.observation import TrackObservation
from tests.fixtures.synthetic_fall_fixtures import (
    LEFT_ANKLE,
    LEFT_HIP,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_SHOULDER,
    build_track_observation,
    generate_bending_sequence,
    generate_fall_sequence,
    generate_fall_with_recovery_sequence,
    generate_sitting_sequence,
    generate_slow_liedown_sequence,
    generate_walking_sequence,
    interpolate_poses,
    make_bending_pose,
    make_fallen_pose,
    make_keypoints,
    make_sitting_pose,
    make_standing_pose,
    mask_missing_keypoints,
    populate_history_from_sequence,
)

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics")


def test_make_keypoints_valid() -> None:
    """Verify make_keypoints builds 17 valid Keypoint objects with expected presence."""
    coords = {
        NOSE: (320.0, 100.0, 0.95),
        LEFT_SHOULDER: (280.0, 150.0),  # uses default_conf
        RIGHT_SHOULDER: (360.0, 150.0),
        LEFT_ANKLE: None,  # absent
    }
    kpts = make_keypoints(coords, default_conf=0.85)
    assert len(kpts) == KEYPOINT_COUNT
    assert all(isinstance(k, Keypoint) for k in kpts)

    # Nose
    assert kpts[NOSE].present is True
    assert kpts[NOSE].x == 320.0
    assert kpts[NOSE].y == 100.0
    assert kpts[NOSE].confidence == 0.95

    # Shoulder with default conf
    assert kpts[LEFT_SHOULDER].present is True
    assert kpts[LEFT_SHOULDER].x == 280.0
    assert kpts[LEFT_SHOULDER].confidence == 0.85

    # Absent ankle
    assert kpts[LEFT_ANKLE].present is False
    assert kpts[LEFT_ANKLE].x is None
    assert kpts[LEFT_ANKLE].y is None


def test_make_standing_pose_contract() -> None:
    """Verify make_standing_pose adheres to PersonPose contract and upright geometry."""
    pose = make_standing_pose(center_x=300.0, base_y=400.0, height=300.0, width=100.0)
    assert isinstance(pose, PersonPose)
    assert len(pose.keypoints) == 17
    assert all(k.present for k in pose.keypoints)

    x1, y1, x2, y2 = pose.bbox_xyxy
    assert x1 < x2 and y1 < y2
    bbox_h = y2 - y1
    bbox_w = x2 - x1
    aspect_ratio = bbox_h / bbox_w
    assert aspect_ratio > 2.0  # Upright human aspect ratio

    # Verify head is higher than hips, hips higher than ankles
    head_y = pose.keypoints[NOSE].y
    hip_y = pose.keypoints[LEFT_HIP].y
    ankle_y = pose.keypoints[LEFT_ANKLE].y
    assert head_y is not None and hip_y is not None and ankle_y is not None
    assert head_y < hip_y < ankle_y


def test_make_sitting_pose_contract() -> None:
    """Verify make_sitting_pose produces valid seated posture with lowered hips."""
    pose = make_sitting_pose(center_x=320.0, seat_y=360.0)
    assert isinstance(pose, PersonPose)
    assert len(pose.keypoints) == 17

    x1, y1, x2, y2 = pose.bbox_xyxy
    bbox_h = y2 - y1
    bbox_w = x2 - x1
    aspect_ratio = bbox_h / bbox_w
    assert 1.0 <= aspect_ratio <= 1.8  # Seated aspect ratio is moderately reduced


def test_make_bending_pose_contract() -> None:
    """Verify make_bending_pose produces forward-shifted head/shoulders."""
    pose = make_bending_pose(center_x=320.0, base_y=440.0, bend_forward_offset=80.0)
    assert isinstance(pose, PersonPose)
    assert len(pose.keypoints) == 17

    nose_x = pose.keypoints[NOSE].x
    hip_x = pose.keypoints[LEFT_HIP].x
    assert nose_x is not None and hip_x is not None
    assert nose_x > hip_x  # Torso shifted forward


def test_make_fallen_pose_contract() -> None:
    """Verify make_fallen_pose produces horizontal posture with aspect ratio << 1.0."""
    pose = make_fallen_pose(center_x=320.0, floor_y=440.0, length=260.0, thickness=70.0)
    assert isinstance(pose, PersonPose)
    assert len(pose.keypoints) == 17

    x1, y1, x2, y2 = pose.bbox_xyxy
    bbox_h = y2 - y1
    bbox_w = x2 - x1
    aspect_ratio = bbox_h / bbox_w
    assert aspect_ratio < 0.5  # Horizontal aspect ratio

    # Keypoints should all lie in a horizontal band near the floor
    for k in pose.keypoints:
        if k.present and k.y is not None:
            assert y1 - 10.0 <= k.y <= y2 + 10.0


def test_interpolate_poses() -> None:
    """Verify linear interpolation between two poses at boundary and intermediate alphas."""
    pose_a = make_standing_pose(center_x=100.0, base_y=400.0)
    pose_b = make_fallen_pose(center_x=300.0, floor_y=400.0)

    # Alpha 0.0 -> matches pose_a
    p0 = interpolate_poses(pose_a, pose_b, 0.0)
    assert p0.bbox_xyxy == pytest.approx(pose_a.bbox_xyxy)
    assert p0.keypoints[NOSE].x == pytest.approx(pose_a.keypoints[NOSE].x)

    # Alpha 1.0 -> matches pose_b
    p1 = interpolate_poses(pose_a, pose_b, 1.0)
    assert p1.bbox_xyxy == pytest.approx(pose_b.bbox_xyxy)
    assert p1.keypoints[NOSE].x == pytest.approx(pose_b.keypoints[NOSE].x)

    # Alpha 0.5 -> midpoint
    p_mid = interpolate_poses(pose_a, pose_b, 0.5)
    expected_x = 0.5 * pose_a.keypoints[NOSE].x + 0.5 * pose_b.keypoints[NOSE].x  # type: ignore[operator]
    assert p_mid.keypoints[NOSE].x == pytest.approx(expected_x)


def test_generate_walking_sequence() -> None:
    """Verify walking sequence properties: frame count, monotonicity, upright aspect ratio."""
    seq = generate_walking_sequence(duration_sec=1.0, fps=10.0, start_time=0.0)
    assert len(seq) == 10
    assert all(isinstance(obs, TrackObservation) for obs in seq)

    # Timestamp monotonicity
    timestamps = [obs.timestamp for obs in seq]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == pytest.approx(0.0)
    assert timestamps[-1] == pytest.approx(0.9)

    # Steady upright posture
    for obs in seq:
        x1, y1, x2, y2 = obs.bbox_xyxy
        assert (y2 - y1) / (x2 - x1) > 1.8


def test_generate_sitting_sequence() -> None:
    """Verify sitting sequence properties: initial standing -> descent -> stable seated."""
    seq = generate_sitting_sequence(
        duration_sec=3.0, fps=10.0, sit_start_sec=1.0, sit_duration_sec=1.0
    )
    assert len(seq) == 30

    # Initial frame is upright standing
    obs_start = seq[0]
    h_start = obs_start.bbox_xyxy[3] - obs_start.bbox_xyxy[1]

    # Final frame is seated (lower top bound, lower height)
    obs_end = seq[-1]
    h_end = obs_end.bbox_xyxy[3] - obs_end.bbox_xyxy[1]
    assert h_end < h_start


def test_generate_bending_sequence() -> None:
    """Verify bending sequence tilts forward then recovers to initial posture."""
    seq = generate_bending_sequence(duration_sec=2.5, fps=10.0, bend_start_sec=0.5)
    assert len(seq) == 25

    # First and last frames are upright standing
    first_obs = seq[0]
    last_obs = seq[-1]
    mid_obs = seq[12]  # in bending hold phase

    assert first_obs.bbox_xyxy[1] == pytest.approx(last_obs.bbox_xyxy[1], abs=5.0)
    # Mid frame has lowered top bound / shifted bbox
    assert mid_obs.bbox_xyxy[0] != first_obs.bbox_xyxy[0]


def test_generate_slow_liedown_sequence() -> None:
    """Verify slow lie-down sequence transitions over several seconds."""
    seq = generate_slow_liedown_sequence(duration_sec=4.0, fps=10.0, transition_duration_sec=2.5)
    assert len(seq) == 40
    assert seq[0].timestamp == pytest.approx(0.0)
    assert seq[-1].timestamp == pytest.approx(3.9)


def test_generate_fall_sequence() -> None:
    """Verify fall sequence has high initial aspect ratio and low final aspect ratio."""
    seq = generate_fall_sequence(
        duration_sec=3.0, fps=15.0, fall_start_sec=1.0, descent_duration_sec=0.35
    )
    assert len(seq) == 45

    # Pre-fall (frame 5 = 0.33s)
    pre_fall = seq[5]
    h_pre = pre_fall.bbox_xyxy[3] - pre_fall.bbox_xyxy[1]
    w_pre = pre_fall.bbox_xyxy[2] - pre_fall.bbox_xyxy[0]
    assert h_pre / w_pre > 2.0

    # Post-fall (frame 30 = 2.0s)
    post_fall = seq[30]
    h_post = post_fall.bbox_xyxy[3] - post_fall.bbox_xyxy[1]
    w_post = post_fall.bbox_xyxy[2] - post_fall.bbox_xyxy[0]
    assert h_post / w_post < 0.5


def test_generate_fall_with_recovery_sequence() -> None:
    """Verify fall with recovery shows standing -> fallen -> standing progression."""
    seq = generate_fall_with_recovery_sequence(
        duration_sec=5.0,
        fps=10.0,
        fall_start_sec=1.0,
        descent_duration_sec=0.3,
        down_duration_sec=1.5,
        recovery_duration_sec=1.5,
    )
    assert len(seq) == 50

    # Pre-fall
    assert (seq[5].bbox_xyxy[3] - seq[5].bbox_xyxy[1]) > 250.0
    # Down state
    assert (seq[25].bbox_xyxy[3] - seq[25].bbox_xyxy[1]) < 100.0
    # Recovered state
    assert (seq[48].bbox_xyxy[3] - seq[48].bbox_xyxy[1]) > 250.0


def test_mask_missing_keypoints() -> None:
    """Verify mask_missing_keypoints sets targeted keypoints to absent."""
    pose = make_standing_pose()
    obs = build_track_observation(pose, camera_id="cam-01", track_id=1, timestamp=1.0)

    masked_obs = mask_missing_keypoints(obs, [LEFT_ANKLE, RIGHT_ANKLE])
    assert masked_obs.keypoints[LEFT_ANKLE].present is False
    assert masked_obs.keypoints[LEFT_ANKLE].x is None
    assert masked_obs.keypoints[RIGHT_ANKLE].present is False
    assert masked_obs.keypoints[NOSE].present is True


def test_populate_history_from_sequence() -> None:
    """Verify populating TrackHistory from a generated sequence."""
    seq = generate_walking_sequence(duration_sec=1.0, fps=10.0)
    history = populate_history_from_sequence(seq)
    assert isinstance(history, TrackHistory)
    assert len(history) == 1
    snap = history.snapshot("cam-01", 1)
    assert len(snap) == 10
    assert snap[0].timestamp == seq[0].timestamp
    assert snap[-1].timestamp == seq[-1].timestamp


def test_framework_freedom_and_cpu_safety() -> None:
    """Verify that the synthetic fixtures module does not import heavy frameworks."""
    import tests.fixtures.synthetic_fall_fixtures as fixtures_mod

    module_path = Path(fixtures_mod.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))

    imported_roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.append(node.module.split(".")[0])

    for forbidden in _FORBIDDEN_RUNTIME_MODULES:
        assert forbidden not in imported_roots, f"Forbidden module {forbidden} imported in fixtures"
        assert forbidden not in sys.modules, f"Forbidden module {forbidden} present in sys.modules"
