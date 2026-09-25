# ruff: noqa: E501
"""Unit tests for Camera Orientation & Height Invariance Normalizer (Phase 11.7 P11.7-013)."""

from __future__ import annotations

import math
import numpy as np
import pytest

from eldercare.fall_engine.normalization.camera_normalizer import (
    CameraNormalizationConfig,
    CameraPerspectiveNormalizer,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_sample_keypoint(x: float, y: float) -> Keypoint:
    return Keypoint(present=True, x=float(x), y=float(y), confidence=0.95)


def _make_track_obs(t: float, h: float, w: float = 80.0) -> TrackObservation:
    kpts = tuple(_make_sample_keypoint(320.0, 240.0) for _ in range(17))
    return TrackObservation(
        camera_id="cam_norm",
        track_id=1,
        timestamp=float(t),
        bbox_xyxy=(320.0 - w / 2, 240.0 - h / 2, 320.0 + w / 2, 240.0 + h / 2),
        detection_confidence=0.95,
        keypoints=kpts,
        image_width=640,
        image_height=480,
    )


def test_camera_normalization_config_defaults():
    """Verify default camera normalization parameters."""
    cfg = CameraNormalizationConfig()
    assert cfg.enabled is True
    assert cfg.camera_height_meters == 2.4
    assert cfg.camera_pitch_deg == 25.0
    assert cfg.focal_length_px == 500.0


def test_identity_normalization_disabled():
    """Verify that disabled normalizer returns values unchanged."""
    normalizer = CameraPerspectiveNormalizer(CameraNormalizationConfig(enabled=False))

    vy_in = 0.75
    vy_out = normalizer.rectify_vertical_velocity(vy_in)
    assert vy_out == vy_in

    angle_in = 45.0
    angle_out = normalizer.rectify_torso_angle(angle_in)
    assert angle_out == angle_in


def test_pitch_rectification_vertical_velocity():
    """Verify that downward camera pitch compensates for perspective foreshortening."""
    # 30 degree pitch -> cos(30) = 0.866 -> factor = 1 / 0.866 = 1.155
    normalizer = CameraPerspectiveNormalizer(CameraNormalizationConfig(camera_pitch_deg=30.0))

    vy_raw = 0.60
    vy_rect = normalizer.rectify_vertical_velocity(vy_raw)
    assert vy_rect > vy_raw
    assert math.isclose(vy_rect, vy_raw / math.cos(math.radians(30.0)), rel_tol=1e-3)


def test_torso_angle_rectification():
    """Verify that torso angle is de-rotated to gravity normal plane."""
    normalizer = CameraPerspectiveNormalizer(CameraNormalizationConfig(camera_pitch_deg=30.0))

    angle_2d = 45.0
    angle_world = normalizer.rectify_torso_angle(angle_2d)
    assert angle_world > angle_2d
    assert angle_world <= 90.0


def test_distance_estimation_near_and_far():
    """Verify distance estimation scales inversely with bounding box height."""
    normalizer = CameraPerspectiveNormalizer()

    # Near person (large bbox h=350px)
    dist_near = normalizer.estimate_distance_to_person(bbox_height_px=350.0, foot_y_px=400.0)

    # Far person (small bbox h=120px)
    dist_far = normalizer.estimate_distance_to_person(bbox_height_px=120.0, foot_y_px=280.0)

    assert dist_near < dist_far
    assert 1.0 < dist_near < 5.0
    assert 4.0 < dist_far < 15.0


def test_keypoint_perspective_projection():
    """Verify keypoints are projected through inverse camera pitch without NaNs."""
    normalizer = CameraPerspectiveNormalizer(CameraNormalizationConfig(camera_pitch_deg=25.0))

    kpts_in = tuple(_make_sample_keypoint(320.0, 100.0 + i * 20.0) for i in range(17))
    kpts_out = normalizer.rectify_keypoints(kpts_in, image_width_px=640.0, image_height_px=480.0)

    assert len(kpts_out) == 17
    for k in kpts_out:
        assert k.present is True
        assert not np.isnan(k.x)
        assert not np.isnan(k.y)
        assert not np.isinf(k.x)
        assert not np.isinf(k.y)


def test_auto_calibration_from_upright_tracks():
    """Verify camera pitch auto-calibration from observed upright aspect ratios."""
    normalizer = CameraPerspectiveNormalizer()

    # Create upright observations with foreshortened aspect ratio (h=160, w=100 -> aspect=1.6)
    # nominal aspect = 2.0 -> cos(pitch) = 1.6 / 2.0 = 0.8 -> pitch = acos(0.8) ~ 36.87 deg
    tracks = [_make_track_obs(t=i * 0.0333, h=160.0, w=100.0) for i in range(30)]

    estimated_pitch = normalizer.auto_calibrate_pitch_from_upright_tracks(tracks)
    assert 30.0 < estimated_pitch < 45.0
