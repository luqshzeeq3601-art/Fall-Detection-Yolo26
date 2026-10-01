# ruff: noqa: N803, N806, E501
"""Phase 11.7 V4 Real-World Data Augmentation Framework.

Provides physical and kinematic augmentations strictly for development partition data:
- Temporal speed scaling (+/- 25% speed variation)
- Camera mounting tilt perturbations (+/- 10 degrees)
- Keypoint occlusion dropouts and confidence noise
- Tracking gap injection (simulating ByteTrack temporary dropouts)
- Aspect ratio distortion (clothing, wide angle lens effects)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
)


@dataclass(frozen=True)
class AugmentationPerturbationConfig:
    """Configuration for physical and environmental track perturbations."""

    speed_scale_range: tuple[float, float] = (0.75, 1.25)
    camera_tilt_angle_range_deg: tuple[float, float] = (-10.0, 10.0)
    aspect_ratio_noise_range: tuple[float, float] = (-0.15, 0.15)
    keypoint_occlusion_rate: float = 0.25
    max_occluded_keypoints: int = 5
    tracking_gap_prob: float = 0.30
    max_gap_duration_sec: float = 0.25
    confidence_jitter_sigma: float = 0.08
    random_seed: int = 42


class V4FeatureAugmenter:
    """Applies realistic physical and sensor transformations to 24-dim feature vectors."""

    def __init__(
        self,
        config: AugmentationPerturbationConfig | None = None,
        seed: int = 42,
    ) -> None:
        self.config = config or AugmentationPerturbationConfig()
        self.rng = np.random.default_rng(seed)

    def augment_vector(self, feat_vec: np.ndarray, is_fall: bool = False) -> np.ndarray:
        """Apply coupled physical perturbations to a single 24-dimensional feature vector.

        Feature Indices:
        0: scale_norm_vel
        1: scale_norm_peak_vel
        2: norm_disp
        3: aspect_ratio
        4: aspect_rel_change
        5: torso_angle_deg
        6: torso_angle_change
        7: h_change_ratio
        8: low_posture_duration
        9: post_descent_stability
        10: avg_keypoint_confidence
        11: hip_height_ratio
        12: centroid_acceleration
        13: angular_velocity_deg_per_sec
        14: angular_acceleration
        15: floor_proximity_ratio
        16: cumulative_descent_distance
        17: velocity_direction_angle
        18: track_age_seconds
        19: track_gap_count
        20: max_gap_duration_seconds
        21: keypoint_availability_rate
        22: shoulder_width_ratio
        23: body_compactness
        """
        vec = np.copy(feat_vec).astype(np.float32)

        # 1. Temporal Speed Dilation: scale velocities and accelerations
        speed_factor = float(self.rng.uniform(*self.config.speed_scale_range))
        vec[0] *= speed_factor  # scale_norm_vel
        vec[1] *= speed_factor  # scale_norm_peak_vel
        vec[12] *= speed_factor**2  # centroid_acceleration
        vec[13] *= speed_factor  # angular_velocity_deg_per_sec
        vec[14] *= speed_factor**2  # angular_acceleration

        # 2. Camera Mounting Tilt: affects torso angle and aspect ratios
        tilt_deg = float(self.rng.uniform(*self.config.camera_tilt_angle_range_deg))
        cos_tilt = max(0.6, math.cos(math.radians(tilt_deg)))
        vec[5] = float(np.clip(vec[5] + tilt_deg, 0.0, 90.0))  # torso_angle_deg
        vec[6] += tilt_deg * 0.5  # torso_angle_change
        vec[3] *= cos_tilt  # aspect_ratio

        # 3. Keypoint Occlusion & Confidence Noise
        if self.rng.random() < self.config.keypoint_occlusion_rate:
            n_occluded = int(self.rng.integers(1, self.config.max_occluded_keypoints + 1))
            # Reduce keypoint availability and confidence
            vec[10] = float(np.clip(vec[10] - 0.04 * n_occluded, 0.20, 1.0))
            vec[21] = float(np.clip(vec[21] - (n_occluded / 17.0), 0.35, 1.0))

        # Add Gaussian confidence jitter
        conf_noise = float(self.rng.normal(0.0, self.config.confidence_jitter_sigma))
        vec[10] = float(np.clip(vec[10] + conf_noise, 0.15, 1.0))

        # 4. Tracking Gap Injection: simulates lost track recovery
        if self.rng.random() < self.config.tracking_gap_prob:
            injected_gaps = int(self.rng.integers(1, 4))
            gap_dur = float(self.rng.uniform(0.067, self.config.max_gap_duration_sec))
            vec[19] += injected_gaps  # track_gap_count
            vec[20] = max(vec[20], gap_dur)  # max_gap_duration_seconds

        # 5. Aspect Ratio & Bounding Box Noise
        ar_noise = float(self.rng.uniform(*self.config.aspect_ratio_noise_range))
        vec[3] = float(max(0.15, vec[3] * (1.0 + ar_noise)))

        return vec

    def augment_batch(
        self,
        X: np.ndarray,
        y: np.ndarray,
    ) -> np.ndarray:
        """Augment a 2D batch of feature vectors."""
        X_aug = np.zeros_like(X)
        for i in range(len(X)):
            X_aug[i] = self.augment_vector(X[i], is_fall=bool(y[i] == 1))
        return X_aug


class AugmentedDatasetBuilderV4:
    """Constructs balanced, perturbation-hardened development datasets."""

    @staticmethod
    def build_augmented_dataset(
        X_dev: np.ndarray,
        y_dev: np.ndarray,
        groups_dev: np.ndarray,
        positive_multiplier: int = 4,
        negative_fraction: float = 0.50,
        random_seed: int = 42,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        """Augment dev partition with oversampled perturbed falls and hard ADLs."""
        # Ensure training isolation
        DatasetSplitGuard.enforce_training_isolation("dev", context="Augmented Dataset Build")

        # Check for test subject contamination
        test_subjects = {"subj-07", "subj-08", "subj-09", "subj-10"}
        overlap = set(groups_dev) & test_subjects
        if overlap:
            raise HoldoutAccessError(f"Contaminated groups in dev features: {overlap}")

        pos_idx = np.where(y_dev == 1)[0]
        neg_idx = np.where(y_dev == 0)[0]

        X_parts: list[np.ndarray] = [X_dev]
        y_parts: list[np.ndarray] = [y_dev]
        group_parts: list[np.ndarray] = [groups_dev]

        # 1. Augment positive fall samples multiple times with different seeds
        for m in range(positive_multiplier):
            seed = random_seed + 100 * (m + 1)
            augmenter = V4FeatureAugmenter(seed=seed)
            X_pos_aug = augmenter.augment_batch(X_dev[pos_idx], y_dev[pos_idx])

            X_parts.append(X_pos_aug)
            y_parts.append(np.ones(len(pos_idx), dtype=np.int64))
            group_parts.append(groups_dev[pos_idx])

        # 2. Augment a fraction of negative ADL samples with gaps and camera tilts
        rng = np.random.default_rng(random_seed)
        sampled_neg = rng.choice(neg_idx, size=int(len(neg_idx) * negative_fraction), replace=False)
        adl_augmenter = V4FeatureAugmenter(seed=random_seed + 999)
        X_neg_aug = adl_augmenter.augment_batch(X_dev[sampled_neg], y_dev[sampled_neg])

        X_parts.append(X_neg_aug)
        y_parts.append(np.zeros(len(sampled_neg), dtype=np.int64))
        group_parts.append(groups_dev[sampled_neg])

        X_total = np.vstack(X_parts)
        y_total = np.concatenate(y_parts)
        groups_total = np.concatenate(group_parts)

        meta = {
            "original_samples": len(y_dev),
            "original_positives": len(pos_idx),
            "original_negatives": len(neg_idx),
            "augmented_samples": len(y_total),
            "augmented_positives": int(np.sum(y_total == 1)),
            "augmented_negatives": int(np.sum(y_total == 0)),
            "positive_multiplier": positive_multiplier,
            "negative_fraction": negative_fraction,
            "unique_subjects": sorted(set(groups_total)),
        }

        return X_total, y_total, groups_total, meta
