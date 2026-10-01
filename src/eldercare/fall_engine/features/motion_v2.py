"""Scale-normalized temporal motion feature extraction (Phase 11.5 v2).

Provides robust velocity scaling by estimated upright reference height,
dynamic posture transition tracking, and continuous feature vectors.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from eldercare.fall_engine.features.geometry_v2 import (
    PoseGeometryFeaturesV2,
    extract_geometry_features_v2,
)
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class TemporalFeaturesV2:
    """Extracted temporal and scale-normalized motion features over track history.

    Attributes:
        current_geometry: Geometric features of the latest observation.
        initial_geometry: Geometric features of the reference observation in window.
        reference_height: Estimated upright person height in pixels.
        history_duration_seconds: Time span of analyzed window in seconds.
        observation_count: Number of observations included in window.
        vertical_displacement: Change in body_center Y (pixels, positive = downward).
        normalized_vertical_displacement: Displacement / reference_height.
        vertical_velocity: Downward velocity in pixels/second.
        scale_normalized_vertical_velocity: Velocity in reference-heights/second.
        peak_vertical_velocity: Peak instantaneous downward velocity (pixels/s).
        scale_normalized_peak_velocity: Peak velocity in reference-heights/second.
        bbox_height_change_ratio: (current_h - ref_h) / ref_h.
        aspect_ratio_relative_change: (current_aspect - ref_aspect) / ref_aspect.
        torso_angle_change_deg: current_angle - ref_angle (degrees).
        low_posture_duration_seconds: Continuous duration (seconds) of low posture.
        post_descent_motion_stability: Velocity variance during low posture.
        average_keypoint_confidence: Mean keypoint confidence across history.
        feature_vector: Standardized 12-dimensional feature vector for classification.
    """

    current_geometry: PoseGeometryFeaturesV2
    initial_geometry: PoseGeometryFeaturesV2
    reference_height: float
    history_duration_seconds: float
    observation_count: int
    vertical_displacement: float
    normalized_vertical_displacement: float
    vertical_velocity: float
    scale_normalized_vertical_velocity: float
    peak_vertical_velocity: float
    scale_normalized_peak_velocity: float
    bbox_height_change_ratio: float
    aspect_ratio_relative_change: float
    torso_angle_change_deg: float
    low_posture_duration_seconds: float
    post_descent_motion_stability: float
    average_keypoint_confidence: float
    feature_vector: tuple[float, ...]


def _compute_low_posture_duration_v2(
    geometries: Sequence[tuple[float, PoseGeometryFeaturesV2]],
    *,
    aspect_threshold: float,
    angle_threshold_deg: float,
) -> float:
    """Calculate the continuous duration (seconds) of recent low posture."""
    if not geometries:
        return 0.0

    t_latest = geometries[-1][0]
    t_start = t_latest

    for t, geom in reversed(geometries):
        is_low = (geom.aspect_ratio <= aspect_threshold) or (
            geom.torso_angle_deg <= angle_threshold_deg
        )
        if is_low:
            t_start = t
        else:
            break

    return max(0.0, t_latest - t_start)


def _compute_post_descent_stability_v2(
    geometries: Sequence[tuple[float, PoseGeometryFeaturesV2]],
    *,
    aspect_threshold: float,
    angle_threshold_deg: float,
) -> float:
    """Calculate motion instability during recent low-posture frames."""
    low_frames = [
        (t, geom)
        for t, geom in geometries
        if (geom.aspect_ratio <= aspect_threshold) or (geom.torso_angle_deg <= angle_threshold_deg)
    ]

    if len(low_frames) < 2:
        return 0.0

    speeds: list[float] = []
    for i in range(1, len(low_frames)):
        dt = max(1e-4, low_frames[i][0] - low_frames[i - 1][0])
        dy = abs(low_frames[i][1].body_center[1] - low_frames[i - 1][1].body_center[1])
        dx = abs(low_frames[i][1].body_center[0] - low_frames[i - 1][1].body_center[0])
        speeds.append(math.sqrt(dx * dx + dy * dy) / dt)

    if not speeds:
        return 0.0

    mean_s = sum(speeds) / len(speeds)
    var = sum((s - mean_s) ** 2 for s in speeds) / len(speeds)
    return math.sqrt(var)


def extract_temporal_features_v2(
    history: Sequence[Any],
    *,
    window_seconds: float = 1.2,
    low_aspect_threshold: float = 0.95,
    low_angle_threshold_deg: float = 45.0,
) -> TemporalFeaturesV2:
    """Extract scale-normalized temporal motion features over TrackObservation history.

    Args:
        history: Sequence of TrackObservation instances ordered from oldest to newest.
        window_seconds: Sliding window lookback duration in seconds.
        low_aspect_threshold: Aspect ratio threshold below which posture is low.
        low_angle_threshold_deg: Torso orientation angle below which posture is horizontal.

    Returns:
        TemporalFeaturesV2 with normalized metrics and feature vector.
    """
    if not history:
        raise ValueError("history sequence must not be empty")

    for i, item in enumerate(history):
        if not isinstance(item, TrackObservation):
            raise TypeError(
                f"history item {i} must be a TrackObservation, got {type(item).__name__}"
            )

    # Validate monotonic timestamps
    for i in range(1, len(history)):
        if history[i].timestamp < history[i - 1].timestamp:
            raise ValueError(
                f"out-of-order timestamp at index {i}: "
                f"{history[i].timestamp!r} < {history[i - 1].timestamp!r}"
            )

    t_newest = history[-1].timestamp
    t_cutoff = max(0.0, t_newest - window_seconds)

    # Full-history geometries for robust standing reference calculation
    all_geoms = [extract_geometry_features_v2(obs) for obs in history]

    # Calculate reference upright height (max or 90th percentile of upright frames)
    upright_heights = [g.bbox_height for g in all_geoms if g.aspect_ratio >= 1.1]
    if upright_heights:
        ref_h = max(upright_heights)
    else:
        ref_h = max(g.bbox_height for g in all_geoms)
    ref_h = max(ref_h, 30.0)

    # Reference aspect ratio from upright frames or oldest frame
    upright_aspects = [g.aspect_ratio for g in all_geoms if g.aspect_ratio >= 1.1]
    ref_aspect = upright_aspects[0] if upright_aspects else all_geoms[0].aspect_ratio
    ref_aspect = max(ref_aspect, 0.4)

    # Windowed slice
    window_tuples: list[tuple[float, PoseGeometryFeaturesV2]] = [
        (obs.timestamp, g)
        for obs, g in zip(history, all_geoms, strict=False)
        if obs.timestamp >= t_cutoff
    ]
    if not window_tuples:
        window_tuples = [(history[-1].timestamp, all_geoms[-1])]

    init_t, init_geom = window_tuples[0]
    curr_t, curr_geom = window_tuples[-1]
    dt = max(0.0, curr_t - init_t)

    # Downward displacement & velocity
    vert_disp = curr_geom.body_center[1] - init_geom.body_center[1]
    norm_disp = vert_disp / ref_h

    if dt > 1e-5:
        vert_vel = vert_disp / dt
        scale_norm_vel = norm_disp / dt
    else:
        vert_vel = 0.0
        scale_norm_vel = 0.0

    # Instantaneous peak velocity across adjacent frame pairs in window
    peak_vel = 0.0
    for i in range(1, len(window_tuples)):
        p_dt = max(1e-4, window_tuples[i][0] - window_tuples[i - 1][0])
        p_dy = window_tuples[i][1].body_center[1] - window_tuples[i - 1][1].body_center[1]
        inst_vel = p_dy / p_dt
        if inst_vel > peak_vel:
            peak_vel = inst_vel

    scale_norm_peak_vel = peak_vel / ref_h

    # Dynamics relative to reference
    h_change_ratio = (curr_geom.bbox_height - ref_h) / ref_h
    aspect_rel_change = (curr_geom.aspect_ratio - ref_aspect) / ref_aspect
    torso_angle_change = curr_geom.torso_angle_deg - init_geom.torso_angle_deg

    low_dur = _compute_low_posture_duration_v2(
        window_tuples,
        aspect_threshold=low_aspect_threshold,
        angle_threshold_deg=low_angle_threshold_deg,
    )

    stability = _compute_post_descent_stability_v2(
        window_tuples,
        aspect_threshold=low_aspect_threshold,
        angle_threshold_deg=low_angle_threshold_deg,
    )

    avg_conf = sum(g.keypoint_confidence_mean for _, g in window_tuples) / len(window_tuples)

    # 12-dimensional feature vector
    feat_vec = (
        float(scale_norm_vel),
        float(scale_norm_peak_vel),
        float(norm_disp),
        float(curr_geom.aspect_ratio),
        float(aspect_rel_change),
        float(curr_geom.torso_angle_deg),
        float(torso_angle_change),
        float(h_change_ratio),
        float(low_dur),
        float(stability),
        float(avg_conf),
        float(curr_geom.hip_height_ratio),
    )

    return TemporalFeaturesV2(
        current_geometry=curr_geom,
        initial_geometry=init_geom,
        reference_height=ref_h,
        history_duration_seconds=dt,
        observation_count=len(window_tuples),
        vertical_displacement=vert_disp,
        normalized_vertical_displacement=norm_disp,
        vertical_velocity=vert_vel,
        scale_normalized_vertical_velocity=scale_norm_vel,
        peak_vertical_velocity=peak_vel,
        scale_normalized_peak_velocity=scale_norm_peak_vel,
        bbox_height_change_ratio=h_change_ratio,
        aspect_ratio_relative_change=aspect_rel_change,
        torso_angle_change_deg=torso_angle_change,
        low_posture_duration_seconds=low_dur,
        post_descent_motion_stability=stability,
        average_keypoint_confidence=avg_conf,
        feature_vector=feat_vec,
    )
