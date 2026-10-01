# ruff: noqa: E501
"""Unit tests for Complex ADL False-Alert Suppressor (Phase 11.7 P11.7-012)."""

from __future__ import annotations

import numpy as np
import pytest

from eldercare.fall_engine.features.features_v3 import (
    PoseGeometryFeaturesV3,
    TemporalFeaturesV3,
    extract_temporal_features_v3,
)
from eldercare.fall_engine.features.multiscale import extract_multiscale_temporal_features
from eldercare.fall_engine.state_machine.states import FallState
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import TrackFallStateMachineV3
from eldercare.fall_engine.suppression.adl_suppressor import (
    ADLFalseAlertSuppressor,
    ADLSuppressionConfig,
    SuppressionReason,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_observation(
    t: float,
    cx: float = 320.0,
    cy: float = 240.0,
    w: float = 100.0,
    h: float = 200.0,
    angle_deg: float = 85.0,
    ankle_y: float | None = None,
    hip_y: float | None = None,
) -> TrackObservation:
    """Helper to generate realistic Keypoint observations."""
    rad = np.radians(angle_deg)
    half_h = h / 2.0
    dx = half_h * np.cos(rad)
    dy = half_h * np.sin(rad)

    shoulder_x = cx + dx * 0.4
    shoulder_y = cy - dy * 0.4
    actual_hip_x = cx - dx * 0.2
    actual_hip_y = hip_y if hip_y is not None else (cy + dy * 0.2)
    head_x = cx + dx * 0.8
    head_y = cy - dy * 0.8
    actual_ankle_y = ankle_y if ankle_y is not None else (cy + half_h * 0.9)

    kpts = []
    # 0: nose, 1-4: eyes/ears
    kpts.append(Keypoint(present=True, x=head_x, y=head_y, confidence=0.9))
    for _ in range(4):
        kpts.append(Keypoint(present=True, x=head_x, y=head_y, confidence=0.9))
    # 5, 6: shoulders
    kpts.append(Keypoint(present=True, x=shoulder_x - 20, y=shoulder_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=shoulder_x + 20, y=shoulder_y, confidence=0.95))
    # 7, 8: elbows
    kpts.append(Keypoint(present=True, x=shoulder_x - 25, y=shoulder_y + 30, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x + 25, y=shoulder_y + 30, confidence=0.9))
    # 9, 10: wrists
    kpts.append(Keypoint(present=True, x=shoulder_x - 25, y=shoulder_y + 60, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x + 25, y=shoulder_y + 60, confidence=0.9))
    # 11, 12: hips
    kpts.append(Keypoint(present=True, x=actual_hip_x - 15, y=actual_hip_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=actual_hip_x + 15, y=actual_hip_y, confidence=0.95))
    # 13, 14: knees
    knee_y = (actual_hip_y + actual_ankle_y) / 2.0
    kpts.append(Keypoint(present=True, x=actual_hip_x - 15, y=knee_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=actual_hip_x + 15, y=knee_y, confidence=0.9))
    # 15, 16: ankles
    kpts.append(Keypoint(present=True, x=cx - 15, y=actual_ankle_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 15, y=actual_ankle_y, confidence=0.9))

    return TrackObservation(
        camera_id="cam_adl",
        track_id=1,
        timestamp=float(t),
        bbox_xyxy=(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0),
        detection_confidence=0.95,
        keypoints=tuple(kpts),
        image_width=640,
        image_height=480,
    )


def test_adl_suppressor_config_defaults():
    """Verify default ADL suppression parameters."""
    cfg = ADLSuppressionConfig()
    assert cfg.enabled is True
    assert cfg.classifier_veto_threshold == 0.55
    assert cfg.bending_max_kinetic_accel == 0.25
    assert cfg.sitting_min_hip_elevation_ratio == 0.25


def test_suppress_calibrated_classifier_veto():
    """Verify classifier probability below tau_veto (0.55) triggers immediate veto."""
    suppressor = ADLFalseAlertSuppressor()
    history = [_make_observation(t=i * 0.0333) for i in range(30)]
    feats = extract_temporal_features_v3(history)

    # Classifier says 0.42 (below 0.55 veto)
    res = suppressor.evaluate_suppression(feats, history, classifier_probability=0.42)
    assert res.suppressed is True
    assert res.reason == SuppressionReason.CLASSIFIER_VETO
    assert "veto threshold" in res.explanation


def test_suppress_controlled_bending():
    """Verify forward bending (picking up object) with planted feet is suppressed."""
    suppressor = ADLFalseAlertSuppressor()
    # 1.0s standing followed by 0.5s smooth bending (feet stay at y=330.0)
    history = []
    # Standing
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0, ankle_y=300.0))
    # Bending forward smoothly: head/torso moves down, ankles stay at 300.0
    for i in range(1, 16):
        t = 1.0 + i * 0.0333
        frac = i / 15.0
        cy = 100.0 + 40.0 * frac
        h = 200.0 - 90.0 * frac
        ang = 85.0 - 55.0 * frac  # ~30 deg
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang, ankle_y=300.0))

    feats = extract_temporal_features_v3(history)
    res = suppressor.evaluate_suppression(feats, history, classifier_probability=0.60)
    assert res.suppressed is True
    assert res.reason == SuppressionReason.CONTROLLED_BENDING


def test_suppress_controlled_sitting():
    """Verify sitting down on a chair (hip remains elevated) is suppressed."""
    suppressor = ADLFalseAlertSuppressor()
    # 1.0s standing then sitting down on chair (hip sits at y=220, feet at y=300)
    history = []
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0, ankle_y=300.0, hip_y=140.0))
    for i in range(1, 16):
        t = 1.0 + i * 0.0333
        frac = i / 15.0
        cy = 100.0 + 50.0 * frac
        h = 200.0 - 60.0 * frac
        ang = 85.0 - 30.0 * frac  # 55 deg
        hip_y = 140.0 + 50.0 * frac  # hip stays elevated (190 vs ankles at 300)
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang, ankle_y=300.0, hip_y=hip_y))

    feats = extract_temporal_features_v3(history)
    res = suppressor.evaluate_suppression(feats, history, classifier_probability=0.62)
    assert res.suppressed is True
    assert res.reason == SuppressionReason.CONTROLLED_SITTING


def test_suppress_intentional_reclining():
    """Verify intentional reclining / gradual bed transition is suppressed."""
    suppressor = ADLFalseAlertSuppressor()
    # Gradual slow recline onto bed over 2.0s (feet elevate onto bed)
    history = []
    for i in range(60):
        t = i * 0.0333
        frac = i / 60.0
        cy = 100.0 + 80.0 * frac
        h = 200.0 - 110.0 * frac
        ang = 85.0 - 60.0 * frac
        ankle_y = 300.0 - 80.0 * frac
        hip_y = 140.0 + 60.0 * frac
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang, ankle_y=ankle_y, hip_y=hip_y))

    feats = extract_multiscale_temporal_features(history)
    res = suppressor.evaluate_suppression(feats, history, classifier_probability=0.60)
    assert res.suppressed is True
    assert res.reason == SuppressionReason.INTENTIONAL_RECLINING


def test_unsuppressed_genuine_fall():
    """Verify genuine uncontrolled kinetic fall is NOT suppressed."""
    suppressor = ADLFalseAlertSuppressor()
    # Fast uncontrolled fall: rapid drop of 160px in 0.3s, high velocity & acceleration, ankles dislodged
    history = []
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0, ankle_y=300.0, hip_y=140.0))
    for i in range(1, 10):
        t = 1.0 + i * 0.0333
        frac = i / 9.0
        cy = 100.0 + 170.0 * frac
        h = 200.0 - 150.0 * frac
        ang = 85.0 - 75.0 * frac  # 10 deg (flat)
        ankle_y = 300.0 + 60.0 * frac  # ankles fly up/down
        hip_y = 140.0 + 170.0 * frac   # hip hits the ground
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang, ankle_y=ankle_y, hip_y=hip_y))

    feats = extract_temporal_features_v3(history)
    res = suppressor.evaluate_suppression(feats, history, classifier_probability=0.88)
    assert res.suppressed is False
    assert res.reason == SuppressionReason.NONE


def test_state_machine_with_adl_suppression():
    """Verify TrackFallStateMachineV3 suppresses false alerts and stays in NORMAL or returns to NORMAL."""
    sm = TrackFallStateMachineV3(
        camera_id="cam_adl",
        track_id=1,
        config=FallStateMachineConfigV3(enable_adl_suppression=True, classifier_veto_threshold=0.55),
    )

    history = []
    # Standing
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0, ankle_y=300.0))
        st, ev = sm.update(history)
        assert st == FallState.NORMAL
        assert ev is None

    # Forward bending: ankles stationary at 300.0
    for i in range(1, 20):
        t = 1.0 + i * 0.0333
        frac = min(1.0, i / 15.0)
        cy = 100.0 + 45.0 * frac
        h = 200.0 - 90.0 * frac
        ang = 85.0 - 55.0 * frac
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang, ankle_y=300.0))
        st, ev = sm.update(history)
        # Even if candidate was entered, no FallEvent should be emitted
        assert ev is None
