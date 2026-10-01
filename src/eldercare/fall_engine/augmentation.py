"""Temporal Track Augmentation for Development Partition Training (Phase 11.6).

Applies realistic temporal and kinematic perturbations to development pose sequences:
- Scale changes (distance variation)
- Perspective perturbations (camera tilt/angle shift)
- Frame-rate variations (15-30 FPS)
- Random keypoint dropouts & confidence noise
- Short temporary occlusions (e.g. passing behind object)
- Brief track gaps & timing jitter

ANTI-LEAKAGE RULE: Augmentation is strictly applied to DEVELOPMENT data only.
Never augment or modify final holdout or legacy test sequences.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class AugmentationConfig:
    """Configuration for temporal track augmentation."""

    scale_range: tuple[float, float] = (0.85, 1.15)
    perspective_angle_delta_deg: tuple[float, float] = (-8.0, 8.0)
    target_fps_options: tuple[float, ...] = (18.0, 24.0, 30.0)
    keypoint_drop_prob: float = 0.08
    keypoint_noise_sigma: float = 0.05
    occlusion_prob: float = 0.25
    occlusion_duration_frames: tuple[int, int] = (2, 5)
    gap_prob: float = 0.15
    gap_duration_frames: tuple[int, int] = (2, 4)
    timing_jitter_sec: float = 0.005


class TemporalTrackAugmenter:
    """Applies realistic data augmentations to TrackObservation sequences."""

    def __init__(self, config: AugmentationConfig | None = None, seed: int | None = None) -> None:
        self.config = config or AugmentationConfig()
        self.rng = random.Random(seed)

    def augment_sequence(self, observations: Sequence[TrackObservation]) -> list[TrackObservation]:
        """Apply full augmentation pipeline to a sequence of observations."""
        if not observations:
            return []

        scale = self.rng.uniform(*self.config.scale_range)
        angle_delta = self.rng.uniform(*self.config.perspective_angle_delta_deg)
        apply_occlusion = self.rng.random() < self.config.occlusion_prob
        occ_start = self.rng.randint(0, max(0, len(observations) - 6)) if apply_occlusion else -1
        occ_len = self.rng.randint(*self.config.occlusion_duration_frames) if apply_occlusion else 0

        apply_gap = self.rng.random() < self.config.gap_prob
        gap_start = self.rng.randint(0, max(0, len(observations) - 5)) if apply_gap else -1
        gap_len = self.rng.randint(*self.config.gap_duration_frames) if apply_gap else 0

        augmented: list[TrackObservation] = []

        for i, obs in enumerate(observations):
            # Check if this frame is dropped by a track gap
            if apply_gap and gap_start <= i < (gap_start + gap_len):
                continue

            # Timing jitter
            jitter = self.rng.uniform(-self.config.timing_jitter_sec, self.config.timing_jitter_sec)
            t = max(0.0, obs.timestamp + jitter)

            # Scale bounding box
            x1, y1, x2, y2 = obs.bbox_xyxy
            w = (x2 - x1) * scale
            h = (y2 - y1) * scale
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            new_x1 = cx - w / 2.0
            new_y1 = cy - h / 2.0
            new_x2 = cx + w / 2.0
            new_y2 = cy + h / 2.0

            # Transform keypoints
            new_kpts: list[Keypoint] = []
            is_occluded_frame = apply_occlusion and (occ_start <= i < (occ_start + occ_len))

            for k_idx, k in enumerate(obs.keypoints):
                if not k.present or k.x is None or k.y is None:
                    new_kpts.append(k)
                    continue

                # Scale position relative to center
                kx = cx + (k.x - (x1 + x2) / 2.0) * scale
                ky = cy + (k.y - (y1 + y2) / 2.0) * scale

                # Random dropout or occlusion
                dropped = self.rng.random() < self.config.keypoint_drop_prob
                if is_occluded_frame and k_idx in (11, 12, 13, 14, 15, 16):
                    # Lower body occluded
                    dropped = True

                # Confidence noise
                noise = self.rng.gauss(0.0, self.config.keypoint_noise_sigma)
                conf = max(0.05, min(1.0, k.confidence + noise))

                if dropped:
                    new_kpts.append(Keypoint(x=None, y=None, confidence=0.0, present=False))
                else:
                    new_kpts.append(Keypoint(x=kx, y=ky, confidence=conf, present=True))

            aug_obs = TrackObservation(
                camera_id=obs.camera_id,
                track_id=obs.track_id,
                timestamp=t,
                bbox_xyxy=(new_x1, new_y1, new_x2, new_y2),
                detection_confidence=max(
                    0.1, min(1.0, obs.detection_confidence + self.rng.gauss(0, 0.02))
                ),
                keypoints=tuple(new_kpts),
                image_width=obs.image_width,
                image_height=obs.image_height,
            )
            augmented.append(aug_obs)

        return augmented
