"""Unit tests for fall confidence scoring, penalties, and cooldown management (P4-004)."""

from __future__ import annotations

import ast
from pathlib import Path

from eldercare.fall_engine.confidence.calculator import (
    FallConfidenceBreakdown,
    FallConfidenceConfig,
    compute_fall_confidence,
)
from eldercare.fall_engine.confidence.cooldown import (
    CooldownConfig,
    IncidentCooldownManager,
)
from eldercare.fall_engine.features.motion import extract_temporal_features
from tests.fixtures.synthetic_fall_fixtures import (
    LEFT_ANKLE,
    LEFT_KNEE,
    RIGHT_ANKLE,
    RIGHT_KNEE,
    build_track_observation,
    generate_fall_sequence,
    make_fallen_pose,
    mask_missing_keypoints,
)


def test_compute_fall_confidence_high_quality_fall() -> None:
    """A clear fall with full keypoints achieves high composite confidence."""
    fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    # Descent occurs around t=0.5 to 0.85s (frames 7 to 13)
    candidate_feats = extract_temporal_features(fall_seq[:14], window_seconds=0.5)
    floor_feats = extract_temporal_features(fall_seq, window_seconds=0.5)

    breakdown = compute_fall_confidence(
        floor_feats,
        fall_seq,
        down_duration_seconds=1.5,
        candidate_features=candidate_feats,
    )

    assert isinstance(breakdown, FallConfidenceBreakdown)
    assert breakdown.motion_score > 0.6
    assert breakdown.posture_score > 0.7
    assert breakdown.persistence_score == 1.0  # 1.5s >= 1.0s target
    assert breakdown.missing_keypoint_penalty == 0.0  # All 17 keypoints present
    assert breakdown.unstable_track_penalty == 0.0
    assert breakdown.composite_confidence >= 0.75
    assert breakdown.detector_model == "yolo26s-pose.pt"
    assert breakdown.tracker_name == "bytetrack"
    assert "normalized_peak_vertical_velocity" in breakdown.key_contributing_features


def test_missing_keypoints_degrades_confidence_safely() -> None:
    """Missing keypoints safely apply missing_keypoint_penalty without raising errors (AC-026)."""
    fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    feats = extract_temporal_features(fall_seq, window_seconds=0.5)

    # Full keypoints baseline
    full_breakdown = compute_fall_confidence(feats, fall_seq, down_duration_seconds=1.0)

    # Mask out 4 keypoints (knees and ankles)
    masked_seq = [
        mask_missing_keypoints(obs, [LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE])
        for obs in fall_seq
    ]
    masked_breakdown = compute_fall_confidence(feats, masked_seq, down_duration_seconds=1.0)

    assert masked_breakdown.missing_keypoint_penalty > 0.0
    assert masked_breakdown.composite_confidence < full_breakdown.composite_confidence
    # 4 missing out of 17 keypoints -> fraction ~ 4/17 -> penalty ~ 0.20 * (4/17) ~ 0.047
    expected_pen = 0.20 * (4.0 / 17.0)
    assert abs(masked_breakdown.missing_keypoint_penalty - expected_pen) < 0.01


def test_unstable_track_detection_confidence_penalty() -> None:
    """Low detection confidence increases unstable_track_penalty."""
    fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    feats = extract_temporal_features(fall_seq, window_seconds=0.5)

    # Replace last observation with a low detection confidence one
    low_conf_obs = build_track_observation(
        make_fallen_pose(center_x=320.0, floor_y=440.0),
        timestamp=3.0,
    )
    # Manually create observation with detection_confidence=0.30
    object.__setattr__(low_conf_obs, "detection_confidence", 0.30)
    low_conf_seq = list(fall_seq[:-1]) + [low_conf_obs]

    breakdown = compute_fall_confidence(feats, low_conf_seq, down_duration_seconds=1.0)
    assert breakdown.unstable_track_penalty > 0.05


def test_custom_confidence_weights_and_thresholds() -> None:
    """Custom configuration overrides default weights and thresholds."""
    fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
    feats = extract_temporal_features(fall_seq, window_seconds=0.5)

    custom_cfg = FallConfidenceConfig(
        weight_motion=0.80,
        weight_posture=0.10,
        weight_persistence=0.10,
        detector_model="custom-pose.pt",
        config_version="2.1.0",
    )
    breakdown = compute_fall_confidence(
        feats, fall_seq, down_duration_seconds=1.0, config=custom_cfg
    )
    assert breakdown.detector_model == "custom-pose.pt"
    assert breakdown.config_version == "2.1.0"


def test_cooldown_manager_throttles_within_window() -> None:
    """Cooldown manager suppresses alerts within incident_cooldown_sec (AC-025)."""
    cfg = CooldownConfig(incident_cooldown_sec=5.0, camera_cooldown_sec=1.0)
    mgr = IncidentCooldownManager(config=cfg)

    # Initial state: not in cooldown
    assert not mgr.is_in_cooldown("cam-01", 1, timestamp=10.0)

    # Record incident at t=10.0
    mgr.record_incident("cam-01", 1, timestamp=10.0)

    # At t=12.0 (2s elapsed < 5s): in cooldown
    assert mgr.is_in_cooldown("cam-01", 1, timestamp=12.0)

    # At t=14.99 (4.99s elapsed < 5s): in cooldown
    assert mgr.is_in_cooldown("cam-01", 1, timestamp=14.99)

    # At t=15.01 (5.01s elapsed >= 5s): cooldown expired
    assert not mgr.is_in_cooldown("cam-01", 1, timestamp=15.01)


def test_cooldown_manager_camera_level_spacing() -> None:
    """Cooldown manager enforces camera_cooldown_sec across different tracks on the same camera."""
    cfg = CooldownConfig(incident_cooldown_sec=5.0, camera_cooldown_sec=1.0)
    mgr = IncidentCooldownManager(config=cfg)

    # Track 1 triggers incident on cam-01 at t=10.0
    mgr.record_incident("cam-01", 1, timestamp=10.0)

    # Track 2 on cam-01 at t=10.5 (0.5s < 1.0s camera spacing): in cooldown
    assert mgr.is_in_cooldown("cam-01", 2, timestamp=10.5)

    # Track 2 on cam-01 at t=11.2 (1.2s >= 1.0s camera spacing): allowed
    assert not mgr.is_in_cooldown("cam-01", 2, timestamp=11.2)

    # Track 3 on different camera (cam-02) at t=10.5: allowed (camera isolated)
    assert not mgr.is_in_cooldown("cam-02", 3, timestamp=10.5)


def test_cooldown_manager_cleanup_expired_and_reset() -> None:
    """Purges aged cooldown records and resets cleanly."""
    mgr = IncidentCooldownManager()
    mgr.record_incident("cam-01", 1, timestamp=10.0)
    mgr.record_incident("cam-02", 2, timestamp=10.0)

    # At t=100.0, records older than 60s are removed
    purged = mgr.cleanup_expired(current_timestamp=100.0, max_idle_sec=60.0)
    assert purged == 2

    # Reset
    mgr.record_incident("cam-01", 1, timestamp=110.0)
    mgr.reset()
    assert not mgr.is_in_cooldown("cam-01", 1, timestamp=111.0)


def test_framework_freedom_ast_scan() -> None:
    """Verify confidence subpackage modules do not import forbidden frameworks."""
    import eldercare.fall_engine.confidence as conf_pkg
    import eldercare.fall_engine.confidence.calculator as calc_mod
    import eldercare.fall_engine.confidence.cooldown as cool_mod

    modules = [conf_pkg, calc_mod, cool_mod]
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
