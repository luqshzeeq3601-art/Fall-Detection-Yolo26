# ruff: noqa: E501
"""Multi-scale temporal context expansion & windowing (Phase 11.7 P11.7-011).

Extracts simultaneous short (0.5s), medium (1.0s), and long (2.0s) temporal context
windows to capture fast kinetic collapses, standard trip dynamics, and slow progressive
slumps without latency penalty.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eldercare.fall_engine.features.features_v3 import (
    PoseGeometryFeaturesV3,
    TemporalFeaturesV3,
    extract_temporal_features_v3,
)
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MultiScaleWindowConfig:
    """Multi-scale temporal window configuration."""

    short_window_sec: float = 0.5   # ~15 frames @ 30fps: captures sharp kinetic impacts / slips
    medium_window_sec: float = 1.0  # ~30 frames @ 30fps: standard trip / forward fall
    long_window_sec: float = 2.0    # ~60 frames @ 30fps: slow slide / gradual faint / collapse
    gap_threshold: float = 0.1      # Track gap threshold in seconds


@dataclass(frozen=True)
class MultiScaleTemporalFeatures:
    """Container holding multi-scale temporal features across 3 horizons."""

    short_features: TemporalFeaturesV3
    medium_features: TemporalFeaturesV3
    long_features: TemporalFeaturesV3
    current_geometry: PoseGeometryFeaturesV3
    reference_height: float
    feature_vector: tuple[float, ...]  # Medium baseline 24-dim feature vector
    multiscale_feature_matrix: np.ndarray  # Shape: (3, 24) [short, medium, long]
    fused_feature_vector: tuple[float, ...]  # Dynamically max-pooled / fused representation

    @property
    def max_scale_normalized_peak_velocity(self) -> float:
        """Max scale-normalized peak vertical velocity across all 3 windows."""
        return max(
            self.short_features.scale_normalized_peak_velocity,
            self.medium_features.scale_normalized_peak_velocity,
            self.long_features.scale_normalized_peak_velocity,
        )

    @property
    def max_scale_normalized_vertical_velocity(self) -> float:
        """Max scale-normalized vertical velocity across all 3 windows."""
        return max(
            self.short_features.scale_normalized_vertical_velocity,
            self.medium_features.scale_normalized_vertical_velocity,
            self.long_features.scale_normalized_vertical_velocity,
        )

    @property
    def max_normalized_vertical_displacement(self) -> float:
        """Max normalized vertical displacement across all 3 windows."""
        return max(
            self.short_features.normalized_vertical_displacement,
            self.medium_features.normalized_vertical_displacement,
            self.long_features.normalized_vertical_displacement,
        )

    @property
    def max_angular_velocity_deg_per_sec(self) -> float:
        """Max absolute angular velocity across all 3 windows."""
        return max(
            abs(self.short_features.angular_velocity_deg_per_sec),
            abs(self.medium_features.angular_velocity_deg_per_sec),
            abs(self.long_features.angular_velocity_deg_per_sec),
        )

    @property
    def max_centroid_acceleration(self) -> float:
        """Max centroid acceleration across all 3 windows."""
        return max(
            self.short_features.centroid_acceleration,
            self.medium_features.centroid_acceleration,
            self.long_features.centroid_acceleration,
        )

    @property
    def min_aspect_ratio_relative_change(self) -> float:
        """Min (largest negative drop) aspect ratio relative change across windows."""
        return min(
            self.short_features.aspect_ratio_relative_change,
            self.medium_features.aspect_ratio_relative_change,
            self.long_features.aspect_ratio_relative_change,
        )

    @property
    def low_posture_duration_seconds(self) -> float:
        """Low posture duration from the long context window."""
        return self.long_features.low_posture_duration_seconds

    @property
    def post_descent_motion_stability(self) -> float:
        """Post descent motion stability from the medium context window."""
        return self.medium_features.post_descent_motion_stability

    @property
    def track_age_seconds(self) -> float:
        """Total observed track age in seconds."""
        return self.long_features.track_age_seconds

    @property
    def track_gap_count(self) -> int:
        """Total tracking gap count in track history."""
        return self.long_features.track_gap_count

    @property
    def floor_proximity_ratio(self) -> float:
        """Floor proximity ratio from current geometry."""
        return self.medium_features.floor_proximity_ratio


def extract_multiscale_temporal_features(
    history: Sequence[TrackObservation],
    config: MultiScaleWindowConfig | None = None,
) -> MultiScaleTemporalFeatures:
    """Extract multi-scale temporal features across short, medium, and long horizons.

    Args:
        history: Sequence of tracked observations sorted chronologically.
        config: MultiScaleWindowConfig specifying window durations.

    Returns:
        MultiScaleTemporalFeatures with all 3 windows and fused properties.
    """
    if config is None:
        config = MultiScaleWindowConfig()

    from eldercare.fall_engine.features.features_v3 import extract_geometry_features_v3
    all_geoms = [extract_geometry_features_v3(obs) for obs in history]

    short_feats = extract_temporal_features_v3(
        history,
        window_seconds=config.short_window_sec,
        gap_threshold=config.gap_threshold,
        all_geoms=all_geoms,
    )
    medium_feats = extract_temporal_features_v3(
        history,
        window_seconds=config.medium_window_sec,
        gap_threshold=config.gap_threshold,
        all_geoms=all_geoms,
    )
    long_feats = extract_temporal_features_v3(
        history,
        window_seconds=config.long_window_sec,
        gap_threshold=config.gap_threshold,
        all_geoms=all_geoms,
    )

    vec_short = np.array(short_feats.feature_vector, dtype=np.float32)
    vec_med = np.array(medium_feats.feature_vector, dtype=np.float32)
    vec_long = np.array(long_feats.feature_vector, dtype=np.float32)

    matrix = np.stack([vec_short, vec_med, vec_long], axis=0)  # Shape: (3, 24)

    # Fused feature vector:
    # Kinematic velocities and displacements take maximum magnitude;
    # Current geometry (aspect ratio, angle, compactness) takes current medium value.
    fused_vec_list = list(vec_med)
    fused_vec_list[0] = float(max(vec_short[0], vec_med[0], vec_long[0]))  # scale_norm_vel
    fused_vec_list[1] = float(max(vec_short[1], vec_med[1], vec_long[1]))  # scale_norm_peak_vel
    fused_vec_list[2] = float(max(vec_short[2], vec_med[2], vec_long[2]))  # norm_disp
    fused_vec_list[4] = float(min(vec_short[4], vec_med[4], vec_long[4]))  # aspect_rel_change (min drop)
    fused_vec_list[6] = float(max(abs(vec_short[6]), abs(vec_med[6]), abs(vec_long[6])))  # torso_angle_change
    fused_vec_list[7] = float(min(vec_short[7], vec_med[7], vec_long[7]))  # h_change_ratio (min drop)
    fused_vec_list[8] = float(long_feats.low_posture_duration_seconds)     # low_posture_duration
    fused_vec_list[12] = float(max(vec_short[12], vec_med[12], vec_long[12]))  # centroid_acceleration
    fused_vec_list[13] = float(max(abs(vec_short[13]), abs(vec_med[13]), abs(vec_long[13])))  # angular_vel
    fused_vec_list[14] = float(max(abs(vec_short[14]), abs(vec_med[14]), abs(vec_long[14])))  # angular_accel
    fused_vec_list[16] = float(max(vec_short[16], vec_med[16], vec_long[16]))  # cumulative_descent

    fused_vec = tuple(float(x) for x in fused_vec_list)

    return MultiScaleTemporalFeatures(
        short_features=short_feats,
        medium_features=medium_feats,
        long_features=long_feats,
        current_geometry=medium_feats.current_geometry,
        reference_height=medium_feats.reference_height,
        feature_vector=medium_feats.feature_vector,
        multiscale_feature_matrix=matrix,
        fused_feature_vector=fused_vec,
    )
