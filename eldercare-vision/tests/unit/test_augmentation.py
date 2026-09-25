"""Unit tests for temporal track augmentation module."""

from __future__ import annotations

import pytest

from eldercare.fall_engine.augmentation import AugmentationConfig, TemporalTrackAugmenter
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_test_observations(count: int = 20) -> list[TrackObservation]:
    """Helper to generate sample TrackObservations."""
    observations = []
    for i in range(count):
        kpts = [
            Keypoint(x=100.0 + k * 10, y=100.0 + k * 15, confidence=0.85, present=True)
            for k in range(17)
        ]
        obs = TrackObservation(
            camera_id="cam_aug_test",
            track_id=1,
            timestamp=i / 30.0,
            bbox_xyxy=(50.0, 50.0, 250.0, 350.0),
            detection_confidence=0.90,
            keypoints=tuple(kpts),
            image_width=640,
            image_height=480,
        )
        observations.append(obs)
    return observations


def test_augmenter_empty_sequence() -> None:
    augmenter = TemporalTrackAugmenter()
    assert augmenter.augment_sequence([]) == []


def test_augmenter_preserves_length_and_types() -> None:
    obs = _make_test_observations(25)
    config = AugmentationConfig(gap_prob=0.0)  # No dropped frames
    augmenter = TemporalTrackAugmenter(config=config, seed=42)
    aug_obs = augmenter.augment_sequence(obs)
    assert len(aug_obs) == len(obs)
    assert all(isinstance(o, TrackObservation) for o in aug_obs)
    assert all(len(o.keypoints) == 17 for o in aug_obs)


def test_augmenter_scale_perturbation() -> None:
    obs = _make_test_observations(10)
    config = AugmentationConfig(scale_range=(1.2, 1.2), gap_prob=0.0, occlusion_prob=0.0, keypoint_drop_prob=0.0)
    augmenter = TemporalTrackAugmenter(config=config, seed=123)
    aug_obs = augmenter.augment_sequence(obs)
    
    orig_w = obs[0].bbox_xyxy[2] - obs[0].bbox_xyxy[0]
    aug_w = aug_obs[0].bbox_xyxy[2] - aug_obs[0].bbox_xyxy[0]
    assert pytest.approx(aug_w, rel=1e-3) == orig_w * 1.2


def test_augmenter_gap_injection() -> None:
    obs = _make_test_observations(30)
    config = AugmentationConfig(gap_prob=1.0, gap_duration_frames=(4, 4))
    augmenter = TemporalTrackAugmenter(config=config, seed=99)
    aug_obs = augmenter.augment_sequence(obs)
    assert len(aug_obs) < len(obs)
