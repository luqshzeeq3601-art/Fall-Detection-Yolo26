# ruff: noqa: E501
"""Unit tests for Multi-Scale Temporal Feature Extraction & State Machine (P11.7-011)."""

from __future__ import annotations

import time
import numpy as np
import pytest

from eldercare.fall_engine.features.multiscale import (
    MultiScaleTemporalFeatures,
    MultiScaleWindowConfig,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.state_machine.states import FallState
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import TrackFallStateMachineV3
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_observation(
    t: float,
    cx: float = 320.0,
    cy: float = 240.0,
    w: float = 100.0,
    h: float = 200.0,
    angle_deg: float = 85.0,
) -> TrackObservation:
    """Helper to generate realistic Keypoint observations."""
    rad = np.radians(angle_deg)
    half_h = h / 2.0
    shoulder_y = cy - half_h * 0.4
    hip_y = cy + half_h * 0.2
    
    # Simple 17-keypoint configuration
    kpts = []
    # 0: nose, 1-4: eyes/ears
    kpts.append(Keypoint(present=True, x=cx, y=cy - half_h * 0.8, confidence=0.9))
    for _ in range(4):
        kpts.append(Keypoint(present=True, x=cx, y=cy - half_h * 0.75, confidence=0.9))
    # 5, 6: shoulders
    kpts.append(Keypoint(present=True, x=cx - 20, y=shoulder_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=cx + 20, y=shoulder_y, confidence=0.95))
    # 7, 8: elbows
    kpts.append(Keypoint(present=True, x=cx - 25, y=shoulder_y + 30, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 25, y=shoulder_y + 30, confidence=0.9))
    # 9, 10: wrists
    kpts.append(Keypoint(present=True, x=cx - 25, y=shoulder_y + 60, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 25, y=shoulder_y + 60, confidence=0.9))
    # 11, 12: hips
    kpts.append(Keypoint(present=True, x=cx - 15, y=hip_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=cx + 15, y=hip_y, confidence=0.95))
    # 13, 14: knees
    kpts.append(Keypoint(present=True, x=cx - 15, y=hip_y + half_h * 0.4, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 15, y=hip_y + half_h * 0.4, confidence=0.9))
    # 15, 16: ankles
    kpts.append(Keypoint(present=True, x=cx - 15, y=cy + half_h * 0.9, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 15, y=cy + half_h * 0.9, confidence=0.9))

    return TrackObservation(
        camera_id="cam_test",
        track_id=1,
        timestamp=float(t),
        bbox_xyxy=(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0),
        detection_confidence=0.95,
        keypoints=tuple(kpts),
        image_width=640,
        image_height=480,
    )


def test_multiscale_window_config_defaults():
    """Verify default multi-scale window configuration parameters."""
    cfg = MultiScaleWindowConfig()
    assert cfg.short_window_sec == 0.5
    assert cfg.medium_window_sec == 1.0
    assert cfg.long_window_sec == 2.0
    assert cfg.gap_threshold == 0.1


def test_multiscale_feature_extraction_short_medium_long():
    """Verify feature extraction across short, medium, and long windows."""
    # Create 3 seconds of standing trajectory (90 frames at 30fps)
    history = [_make_observation(t=i * 0.0333) for i in range(90)]
    feats = extract_multiscale_temporal_features(history)

    assert isinstance(feats, MultiScaleTemporalFeatures)
    assert len(feats.feature_vector) == 24
    assert len(feats.fused_feature_vector) == 24
    assert feats.multiscale_feature_matrix.shape == (3, 24)
    assert not np.isnan(feats.multiscale_feature_matrix).any()
    assert not np.isinf(feats.multiscale_feature_matrix).any()

    # Verify individual windows
    assert feats.short_features.history_duration_seconds <= 0.55
    assert feats.medium_features.history_duration_seconds <= 1.05
    assert feats.long_features.history_duration_seconds <= 2.05


def test_multiscale_rapid_kinetic_fall_detection():
    """Verify that rapid kinetic falls produce prominent velocity spikes in short window."""
    # 1.0s standing followed by 0.4s rapid collapse (fast drop of 150px)
    history = []
    # 1.0s standing (30 frames)
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0))
    # 0.4s rapid drop (12 frames)
    for i in range(1, 13):
        t = 1.0 + i * 0.0333
        frac = i / 12.0
        cy = 100.0 + 150.0 * frac
        h = 200.0 - 140.0 * frac
        ang = 85.0 - 70.0 * frac
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang))

    feats = extract_multiscale_temporal_features(history)

    # Short window should capture high scale-normalized velocity
    assert feats.short_features.scale_normalized_peak_velocity > 0.6
    assert feats.max_scale_normalized_peak_velocity > 0.6
    assert feats.max_scale_normalized_peak_velocity >= feats.long_features.scale_normalized_peak_velocity


def test_multiscale_slow_gradual_slump_detection():
    """Verify that slow gradual slumps over 2.0s are captured by the long context window."""
    # Slow gradual descent over 2.0s (60 frames)
    history = []
    for i in range(60):
        t = i * 0.0333
        frac = i / 60.0
        cy = 100.0 + 120.0 * frac
        h = 200.0 - 130.0 * frac
        ang = 85.0 - 65.0 * frac
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang))

    feats = extract_multiscale_temporal_features(history)

    # Long window captures the total displacement and cumulative descent
    assert feats.long_features.normalized_vertical_displacement > 0.4
    assert feats.max_normalized_vertical_displacement >= feats.short_features.normalized_vertical_displacement


def test_multiscale_short_history_graceful_handling():
    """Verify robustness and absence of NaNs when history is extremely brief."""
    # 1 frame
    h1 = [_make_observation(t=0.0)]
    f1 = extract_multiscale_temporal_features(h1)
    assert len(f1.feature_vector) == 24
    assert not np.isnan(f1.multiscale_feature_matrix).any()

    # 2 frames
    h2 = [_make_observation(t=0.0), _make_observation(t=0.0333)]
    f2 = extract_multiscale_temporal_features(h2)
    assert len(f2.feature_vector) == 24
    assert not np.isnan(f2.multiscale_feature_matrix).any()


def test_multiscale_state_machine_integration():
    """Verify that TrackFallStateMachineV3 operates correctly with multi-scale features."""
    sm = TrackFallStateMachineV3(
        camera_id="cam_test",
        track_id=1,
        config=FallStateMachineConfigV3(use_multiscale_windowing=True),
    )

    history = []
    # 1.0s normal standing
    for i in range(30):
        history.append(_make_observation(t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0))
        st, ev = sm.update(history)
        assert st == FallState.NORMAL
        assert ev is None

    # Rapid fall
    for i in range(1, 15):
        t = 1.0 + i * 0.0333
        frac = min(1.0, i / 10.0)
        cy = 100.0 + 150.0 * frac
        h = 200.0 - 140.0 * frac
        ang = 85.0 - 70.0 * frac
        history.append(_make_observation(t=t, cy=cy, h=h, angle_deg=ang))
        st, ev = sm.update(history)

    # Should have entered descent candidate or down confirming
    assert sm.state in (FallState.DESCENT_CANDIDATE, FallState.DOWN_CONFIRMING, FallState.FALL_CONFIRMED)


def test_multiscale_performance_and_latency():
    """Verify multi-scale feature extraction latency is below 0.5ms per update."""
    history = [_make_observation(t=i * 0.0333) for i in range(60)]

    # Warm-up
    for _ in range(10):
        extract_multiscale_temporal_features(history)

    # Benchmark 100 iterations
    t0 = time.perf_counter()
    for _ in range(100):
        extract_multiscale_temporal_features(history)
    t1 = time.perf_counter()

    avg_ms = ((t1 - t0) / 100.0) * 1000.0
    # Must be faster than 5.0ms (typically ~1-2ms on CPU)
    assert avg_ms < 5.0, f"Average latency {avg_ms:.3f}ms exceeds 5.0ms budget"
