"""Unit tests for Temporal Fall Engine feature extraction (P4-002).

Validates that geometry and motion features are correctly calculated,
confidence-aware, robust to missing keypoints, and deterministic.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eldercare.fall_engine.features import (
    PoseGeometryFeatures,
    TemporalFeatures,
    extract_geometry_features,
    extract_temporal_features,
)
from tests.fixtures.synthetic_fall_fixtures import (
    LEFT_HIP,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    build_track_observation,
    generate_fall_sequence,
    generate_sitting_sequence,
    generate_walking_sequence,
    make_fallen_pose,
    make_keypoints,
    make_standing_pose,
)

_FORBIDDEN_AST_MODULES = ("torch", "ultralytics", "cv2")
_FORBIDDEN_GLOBAL_MODULES = ("torch", "ultralytics")


def test_extract_geometry_standing_upright() -> None:
    """Verify geometry extraction on upright standing pose."""
    pose = make_standing_pose(center_x=320.0, base_y=440.0, height=300.0, width=120.0)
    obs = build_track_observation(pose, timestamp=1.0)
    geom = extract_geometry_features(obs)

    assert isinstance(geom, PoseGeometryFeatures)
    assert geom.bbox_width == pytest.approx(120.0)
    assert geom.bbox_height == pytest.approx(300.0)
    assert geom.aspect_ratio == pytest.approx(2.5)
    assert geom.shoulder_midpoint is not None
    assert geom.hip_midpoint is not None
    assert geom.torso_vector is not None

    # Shoulders are above hips -> dy < 0
    assert geom.torso_vector[1] < 0.0
    # Torso is almost perfectly vertical (85 - 90 degrees)
    assert 80.0 <= geom.torso_angle_deg <= 90.0
    assert geom.keypoints_present_count == 17
    assert geom.keypoint_confidence_mean > 0.85


def test_extract_geometry_fallen_horizontal() -> None:
    """Verify geometry extraction on horizontal lying pose."""
    pose = make_fallen_pose(center_x=320.0, floor_y=440.0, length=260.0, thickness=70.0)
    obs = build_track_observation(pose, timestamp=1.0)
    geom = extract_geometry_features(obs)

    assert geom.aspect_ratio < 0.4
    assert geom.torso_angle_deg < 20.0
    assert geom.shoulder_midpoint is not None
    assert geom.hip_midpoint is not None


def test_extract_geometry_missing_keypoints_fallback() -> None:
    """Verify missing joints fallback gracefully without exceptions."""
    coords = {
        NOSE: (320.0, 100.0),
        LEFT_SHOULDER: (300.0, 150.0),
        RIGHT_SHOULDER: None,  # Right shoulder occluded
        LEFT_HIP: None,
        RIGHT_HIP: None,  # Both hips occluded
    }
    kpts = make_keypoints(coords)
    pose = make_standing_pose()
    # Replace keypoints with sparse set
    pose_sparse = type(pose)(
        bbox_xyxy=pose.bbox_xyxy,
        detection_confidence=pose.detection_confidence,
        keypoints=kpts,
    )
    obs = build_track_observation(pose_sparse)
    geom = extract_geometry_features(obs)

    # Fallback to single shoulder
    assert geom.shoulder_midpoint == pytest.approx((300.0, 150.0))
    # Both hips missing -> None
    assert geom.hip_midpoint is None
    assert geom.torso_vector is None
    # Torso angle falls back to aspect-ratio based estimate
    assert geom.torso_angle_deg >= 80.0
    # Body center falls back to bbox center
    x1, y1, x2, y2 = obs.bbox_xyxy
    assert geom.body_center == pytest.approx(((x1 + x2) / 2.0, (y1 + y2) / 2.0))


def test_extract_temporal_empty_or_invalid_raises() -> None:
    """Verify input validation on history sequence."""
    with pytest.raises(ValueError, match="must not be empty"):
        extract_temporal_features([])

    with pytest.raises(TypeError, match="must be a TrackObservation"):
        extract_temporal_features(["invalid"])  # type: ignore[list-item]

    # Out of order timestamps
    obs1 = build_track_observation(make_standing_pose(), timestamp=2.0)
    obs2 = build_track_observation(make_standing_pose(), timestamp=1.0)
    with pytest.raises(ValueError, match="out-of-order timestamp"):
        extract_temporal_features([obs1, obs2])


def test_extract_temporal_single_observation() -> None:
    """Verify single observation returns zero velocity and displacement."""
    obs = build_track_observation(make_standing_pose(), timestamp=0.5)
    feats = extract_temporal_features([obs])

    assert isinstance(feats, TemporalFeatures)
    assert feats.observation_count == 1
    assert feats.history_duration_seconds == 0.0
    assert feats.vertical_displacement == 0.0
    assert feats.vertical_velocity == 0.0
    assert feats.normalized_vertical_velocity == 0.0
    assert feats.bbox_height_change_ratio == 0.0
    assert feats.aspect_ratio_change == 0.0


def test_extract_temporal_walking_signature() -> None:
    """Verify normal walking produces low vertical velocity and high aspect ratio."""
    seq = generate_walking_sequence(duration_sec=2.0, fps=15.0)
    feats = extract_temporal_features(seq, window_seconds=1.5)

    assert feats.observation_count >= 15
    assert abs(feats.vertical_displacement) < 15.0  # Minimal vertical drift
    assert abs(feats.normalized_vertical_velocity) < 0.2  # Minimal vertical velocity
    assert feats.current_geometry.aspect_ratio > 2.0
    assert feats.low_posture_duration_seconds == 0.0


def test_extract_temporal_sitting_signature() -> None:
    """Verify sitting produces moderate vertical velocity without collapsing aspect ratio."""
    seq = generate_sitting_sequence(
        duration_sec=3.0, fps=15.0, sit_start_sec=0.5, sit_duration_sec=1.5
    )
    # Analyze middle of sitting transition
    mid_history = seq[:20]
    feats = extract_temporal_features(mid_history, window_seconds=1.5)

    # Moderate descent speed (< 1.0 person height/sec)
    assert 0.0 < feats.normalized_vertical_velocity < 0.9
    # Aspect ratio remains moderately upright (e.g. > 1.2)
    assert feats.current_geometry.aspect_ratio >= 1.2
    assert feats.low_posture_duration_seconds == 0.0


def test_extract_temporal_fall_signature() -> None:
    """Verify rapid fall produces velocity spike, angle collapse, and low posture."""
    seq = generate_fall_sequence(
        duration_sec=3.5,
        fps=15.0,
        fall_start_sec=1.0,
        descent_duration_sec=0.35,
    )

    # 1. During rapid descent (at 1.3s, frame ~20)
    descent_history = seq[:21]
    descent_feats = extract_temporal_features(descent_history, window_seconds=0.5)
    # High normalized peak downward velocity (> 1.0 person heights / sec)
    assert descent_feats.normalized_peak_vertical_velocity > 1.0
    assert descent_feats.normalized_vertical_velocity > 0.5
    # Aspect ratio and angle dropped sharply
    assert descent_feats.aspect_ratio_change < -1.0
    assert descent_feats.torso_angle_change_deg < -40.0

    # 2. Post-fall on floor (at 3.0s, frame 45)
    floor_history = seq
    floor_feats = extract_temporal_features(floor_history, window_seconds=1.5)
    # In horizontal posture for > 1.0 second
    assert floor_feats.low_posture_duration_seconds > 1.0
    assert floor_feats.current_geometry.aspect_ratio < 0.5
    # Very low motion instability on floor
    assert floor_feats.post_descent_motion_stability < 10.0


def test_extract_temporal_window_slicing() -> None:
    """Verify window_seconds parameter restricts feature calculation to recent frames."""
    seq = generate_walking_sequence(duration_sec=4.0, fps=10.0)
    # 40 frames total. Window of 1.0s should include ~11 frames
    feats = extract_temporal_features(seq, window_seconds=1.0)
    assert 10 <= feats.observation_count <= 12
    assert feats.history_duration_seconds == pytest.approx(1.0, abs=0.15)


def test_framework_freedom_ast_scan() -> None:
    """Verify feature extractor modules do not import forbidden frameworks."""
    import eldercare.fall_engine.features.geometry as geom_mod
    import eldercare.fall_engine.features.motion as motion_mod

    for mod in (geom_mod, motion_mod):
        mod_path = Path(mod.__file__)
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        imported_roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.append(node.module.split(".")[0])

        for forbidden in _FORBIDDEN_AST_MODULES:
            assert forbidden not in imported_roots, f"Module {mod.__name__} imports {forbidden}"
