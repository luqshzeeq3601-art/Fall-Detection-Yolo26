# ruff: noqa: N803, N806, E501
"""Unit tests for Phase 11.7 V4 Real-World Data Augmentation Framework."""

from __future__ import annotations

import numpy as np
import pytest

from eldercare.fall_engine.dataset.augmented_dataset import (
    AugmentationPerturbationConfig,
    AugmentedDatasetBuilderV4,
    V4FeatureAugmenter,
)
from eldercare.fall_engine.evaluation.split_guard import (
    HoldoutAccessError,
)
from eldercare.fall_engine.learned_classifier.classifier_v4 import (
    GRUClassifierV4,
)


def _make_sample_vector() -> np.ndarray:
    """Generate sample 24-dim feature vector representing a fall."""
    vec = np.zeros(24, dtype=np.float32)
    vec[0] = 0.50  # scale_norm_vel
    vec[1] = 0.80  # scale_norm_peak_vel
    vec[3] = 0.80  # aspect_ratio
    vec[5] = 30.0  # torso_angle_deg
    vec[10] = 0.85  # avg_keypoint_confidence
    vec[19] = 0.0  # track_gap_count
    vec[20] = 0.0  # max_gap_duration_seconds
    vec[21] = 1.0  # keypoint_availability_rate
    return vec


def test_feature_augmenter_speed_scaling() -> None:
    """Verify velocity features are scaled within speed bounds."""
    cfg = AugmentationPerturbationConfig(
        speed_scale_range=(0.80, 1.20),
        camera_tilt_angle_range_deg=(0.0, 0.0),
        keypoint_occlusion_rate=0.0,
        tracking_gap_prob=0.0,
        aspect_ratio_noise_range=(0.0, 0.0),
        confidence_jitter_sigma=0.0,
    )
    augmenter = V4FeatureAugmenter(config=cfg, seed=42)
    sample = _make_sample_vector()

    aug = augmenter.augment_vector(sample, is_fall=True)
    ratio = aug[0] / sample[0]
    assert 0.80 <= ratio <= 1.20
    assert 0.80 <= (aug[1] / sample[1]) <= 1.20


def test_feature_augmenter_tilt_and_aspect() -> None:
    """Verify torso angle and aspect ratio are realistically perturbed."""
    cfg = AugmentationPerturbationConfig(
        speed_scale_range=(1.0, 1.0),
        camera_tilt_angle_range_deg=(-10.0, 10.0),
        keypoint_occlusion_rate=0.0,
        tracking_gap_prob=0.0,
        confidence_jitter_sigma=0.0,
    )
    augmenter = V4FeatureAugmenter(config=cfg, seed=42)
    sample = _make_sample_vector()

    aug = augmenter.augment_vector(sample, is_fall=True)
    assert 20.0 <= aug[5] <= 40.0  # 30 +/- 10 deg
    assert aug[3] > 0.10


def test_feature_augmenter_occlusion_and_gap() -> None:
    """Verify keypoint occlusions and tracking gaps alter feature vector correctly."""
    cfg = AugmentationPerturbationConfig(
        keypoint_occlusion_rate=1.0,
        max_occluded_keypoints=5,
        tracking_gap_prob=1.0,
        max_gap_duration_sec=0.20,
    )
    augmenter = V4FeatureAugmenter(config=cfg, seed=42)
    sample = _make_sample_vector()

    aug = augmenter.augment_vector(sample, is_fall=True)
    assert aug[19] >= 1.0  # Gap injected
    assert aug[20] > 0.0  # Max gap duration > 0
    assert aug[10] <= 0.85 + 0.10  # Reduced/perturbed confidence


def test_augmented_dataset_builder() -> None:
    """Verify augmented dataset builder expands samples while maintaining split isolation."""
    X_dev = np.ones((50, 24), dtype=np.float32)
    y_dev = np.array([1] * 10 + [0] * 40, dtype=np.int64)
    groups_dev = np.array(["subj-01"] * 25 + ["subj-02"] * 25)

    X_aug, y_aug, groups_aug, meta = AugmentedDatasetBuilderV4.build_augmented_dataset(
        X_dev=X_dev,
        y_dev=y_dev,
        groups_dev=groups_dev,
        positive_multiplier=3,
        negative_fraction=0.50,
        random_seed=42,
    )

    # 10 orig pos + (3 * 10) = 40 positive
    # 40 orig neg + (0.5 * 40) = 60 negative
    # Total = 100
    assert len(y_aug) == 100
    assert np.sum(y_aug == 1) == 40
    assert np.sum(y_aug == 0) == 60
    assert set(groups_aug) == {"subj-01", "subj-02"}

    # Test error when holdout subject is present
    contaminated_groups = np.array(["subj-07"] * 50)
    with pytest.raises(HoldoutAccessError):
        AugmentedDatasetBuilderV4.build_augmented_dataset(
            X_dev=X_dev,
            y_dev=y_dev,
            groups_dev=contaminated_groups,
        )


def test_augmented_model_training_and_inference() -> None:
    """Verify training GRU on augmented dataset produces valid model."""
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, size=(60, 24)).astype(np.float32)
    y = np.array([1] * 20 + [0] * 40, dtype=np.int64)

    model = GRUClassifierV4(feature_dim=24, hidden_size=16)
    model.train(X, y, epochs=3, lr=0.01)

    probs = model.predict_batch(X[:5])
    assert len(probs) == 5
    assert all(0.0 <= p <= 1.0 for p in probs)
