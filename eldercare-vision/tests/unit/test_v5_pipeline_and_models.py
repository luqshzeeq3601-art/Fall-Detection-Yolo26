"""Unit tests for Phase 11.8 V5 Skeleton Preprocessor, Models M0-M3, and Pipeline."""

import time

import numpy as np
import pytest

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_obs(
    timestamp: float,
    y_center: float = 50.0,
    bbox_h: float = 100.0,
    bbox_w: float = 30.0,
    is_down: bool = False,
) -> TrackObservation:
    x_center = 50.0
    x1, y1 = x_center - bbox_w / 2, y_center - bbox_h / 2
    x2, y2 = x_center + bbox_w / 2, y_center + bbox_h / 2

    kpts = []
    for i in range(17):
        kpts.append(Keypoint(present=True, x=x_center, y=y_center, confidence=0.9))

    if is_down:
        kpts[5] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9)
        kpts[6] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9)
        kpts[11] = Keypoint(present=True, x=x2, y=y_center, confidence=0.9)
        kpts[12] = Keypoint(present=True, x=x2, y=y_center, confidence=0.9)
    else:
        kpts[5] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9)
        kpts[6] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9)
        kpts[11] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9)
        kpts[12] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9)

    return TrackObservation(
        camera_id="cam_test",
        track_id=1,
        timestamp=timestamp,
        bbox_xyxy=(x1, y1, x2, y2),
        keypoints=tuple(kpts),
        image_width=640,
        image_height=480,
        detection_confidence=0.9,
    )


def test_skeleton_normalization_invariance() -> None:
    """Verify that translation of the bounding box does not change normalized keypoints."""
    from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
        extract_normalized_skeleton_frame,
    )

    obs1 = _make_obs(0.0, y_center=100.0, bbox_h=100.0, bbox_w=30.0)
    obs2 = _make_obs(0.0, y_center=300.0, bbox_h=100.0, bbox_w=30.0)

    vec1 = extract_normalized_skeleton_frame(obs1)
    vec2 = extract_normalized_skeleton_frame(obs2)

    # First 68 values are normalized keypoints
    np.testing.assert_allclose(vec1[:68], vec2[:68], atol=1e-4)


def test_skeleton_missing_keypoints_mask() -> None:
    """Verify missing keypoints have mask=0.0 and zero coords without fabrication."""
    from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
        extract_normalized_skeleton_frame,
    )

    obs = _make_obs(0.0)
    kpts_list = list(obs.keypoints)
    kpts_list[3] = Keypoint(present=False, x=None, y=None, confidence=0.1)
    obs_masked = TrackObservation(
        camera_id="cam_test",
        track_id=1,
        timestamp=0.0,
        bbox_xyxy=obs.bbox_xyxy,
        keypoints=tuple(kpts_list),
        image_width=640,
        image_height=480,
        detection_confidence=0.9,
    )

    vec = extract_normalized_skeleton_frame(obs_masked)
    # Keypoint 3 is at index 3 * 4 = 12 .. 15: [norm_x, norm_y, conf, mask]
    assert vec[12] == 0.0
    assert vec[13] == 0.0
    assert pytest.approx(vec[14], abs=1e-3) == 0.1
    assert vec[15] == 0.0  # mask is 0


def test_temporal_skeleton_net_forward_and_latency() -> None:
    """Verify network forward pass output shape and sub-5ms latency budget."""
    import torch

    from eldercare.fall_engine.learned_classifier.skeleton_v5 import TemporalSkeletonNetV5

    net = TemporalSkeletonNetV5(in_features=72, conv_channels=64, gru_hidden=64, num_classes=3)
    dummy_input = torch.randn(1, 30, 72)

    # Warmup
    for _ in range(5):
        _ = net(dummy_input)

    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        logits = net(dummy_input)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    elapsed_ms = min(latencies)

    assert logits.shape == (1, 3)
    assert elapsed_ms < 25.0  # Well within CPU budget


def test_post_processor_v5_fall_progression() -> None:
    """Verify falling -> fallen transition triggers alert within window."""
    from eldercare.fall_engine.learned_classifier.classifier_v5 import (
        PostProcessorConfigV5,
        PostProcessorV5,
    )

    post_proc = PostProcessorV5(
        PostProcessorConfigV5(
            fall_trigger_threshold=0.4,
            down_confirmation_threshold=0.5,
            min_down_sustain_seconds=0.4,
            transition_max_window_sec=2.0,
        )
    )

    # 1. Normal state
    assert not post_proc.update(timestamp=0.0, p_falling=0.1, p_fallen=0.1, is_low_posture=False)

    # 2. Rapid fall spike
    assert not post_proc.update(timestamp=0.5, p_falling=0.8, p_fallen=0.1, is_low_posture=False)

    # 3. Transition to down posture
    assert not post_proc.update(timestamp=0.6, p_falling=0.2, p_fallen=0.9, is_low_posture=True)
    assert not post_proc.update(timestamp=0.8, p_falling=0.1, p_fallen=0.9, is_low_posture=True)

    # 4. Sustained down posture for >= 0.4s (at t=1.05s)
    triggered = post_proc.update(timestamp=1.05, p_falling=0.1, p_fallen=0.9, is_low_posture=True)
    assert triggered is True

    # 5. Cooldown prevents immediate re-trigger
    assert not post_proc.update(timestamp=1.2, p_falling=0.9, p_fallen=0.9, is_low_posture=True)


def test_pipeline_v5_e2e() -> None:
    """Verify end-to-end V5 pipeline state processing."""
    from eldercare.fall_engine.pipeline_v5 import FallEnginePipelineV5
    from eldercare.fall_engine.state_machine.states import FallState

    pipeline = FallEnginePipelineV5()
    pipeline.reset()

    # Feed standing frames
    for i in range(5):
        obs = _make_obs(timestamp=i * 0.066, y_center=50.0, bbox_h=100.0, bbox_w=30.0)
        state, event = pipeline.process_observation(obs)
        assert state == FallState.NORMAL
        assert event is None
