"""Temporal motion feature extraction over TrackObservation history (P4-002).

Pure, deterministic extraction of motion dynamics, velocity, angle change,
and posture stability per AI_SPEC.md §6.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from eldercare.fall_engine.features.geometry import (
    PoseGeometryFeatures,
    extract_geometry_features,
)
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class TemporalFeatures:
    """Extracted temporal and motion features over a sliding history window.

    Attributes:
        current_geometry: Geometric features of the latest observation.
        initial_geometry: Geometric features of the oldest observation in window.
        history_duration_seconds: Time span of the analyzed window in seconds.
        observation_count: Number of observations included in the window.
        vertical_displacement: Change in body_center Y (pixels, positive = downward).
        normalized_vertical_displacement: Displacement normalized by initial person height.
        vertical_velocity: Average rate of vertical descent in pixels/second.
        normalized_vertical_velocity: Average vertical descent in person-heights/second.
        peak_vertical_velocity: Maximum instantaneous downward velocity in pixels/second.
        normalized_peak_vertical_velocity: Peak downward velocity in person-heights/second.
        bbox_height_change_ratio: (current_h - initial_h) / initial_h.
        aspect_ratio_change: current_aspect_ratio - initial_aspect_ratio.
        torso_angle_change_deg: current_torso_angle - initial_torso_angle (degrees).
        low_posture_duration_seconds: Continuous duration (seconds) of recent low posture.
        post_descent_motion_stability: Velocity variance / motion magnitude in post-descent
            state (lower values indicate still/motionless posture on ground).
        average_keypoint_confidence: Mean keypoint confidence across the history window.
    """

    current_geometry: PoseGeometryFeatures
    initial_geometry: PoseGeometryFeatures
    history_duration_seconds: float
    observation_count: int
    vertical_displacement: float
    normalized_vertical_displacement: float
    vertical_velocity: float
    normalized_vertical_velocity: float
    peak_vertical_velocity: float
    normalized_peak_vertical_velocity: float
    bbox_height_change_ratio: float
    aspect_ratio_change: float
    torso_angle_change_deg: float
    low_posture_duration_seconds: float
    post_descent_motion_stability: float
    average_keypoint_confidence: float


def _compute_low_posture_duration(
    geometries: Sequence[tuple[float, PoseGeometryFeatures]],
    *,
    aspect_threshold: float,
    angle_threshold_deg: float,
) -> float:
    """Calculate the continuous duration (seconds) of recent low posture."""
    if not geometries:
        return 0.0

    t_latest = geometries[-1][0]
    t_start = t_latest

    # Traverse backwards from latest frame
    for t, geom in reversed(geometries):
        is_low = (geom.aspect_ratio <= aspect_threshold) or (
            geom.torso_angle_deg <= angle_threshold_deg
        )
        if is_low:
            t_start = t
        else:
            break

    return max(0.0, t_latest - t_start)


def _compute_post_descent_stability(
    geometries: Sequence[tuple[float, PoseGeometryFeatures]],
    *,
    aspect_threshold: float,
    angle_threshold_deg: float,
) -> float:
    """Calculate motion instability (velocity variance) during recent low-posture frames."""
    low_frames = [
        (t, geom)
        for t, geom in geometries
        if (geom.aspect_ratio <= aspect_threshold) or (geom.torso_angle_deg <= angle_threshold_deg)
    ]

    if len(low_frames) < 2:
        return 0.0

    displacements: list[float] = []
    for i in range(1, len(low_frames)):
        dt = max(1e-4, low_frames[i][0] - low_frames[i - 1][0])
        dy = abs(low_frames[i][1].body_center[1] - low_frames[i - 1][1].body_center[1])
        dx = abs(low_frames[i][1].body_center[0] - low_frames[i - 1][1].body_center[0])
        speed = math.sqrt(dx * dx + dy * dy) / dt
        displacements.append(speed)

    if not displacements:
        return 0.0

    mean_speed = sum(displacements) / len(displacements)
    variance = sum((s - mean_speed) ** 2 for s in displacements) / len(displacements)
    return math.sqrt(variance)


def extract_temporal_features(
    history: Sequence[Any],
    *,
    window_seconds: float = 1.5,
    low_aspect_threshold: float = 0.85,
    low_angle_threshold_deg: float = 40.0,
) -> TemporalFeatures:
    """Extract temporal motion features over a sliding TrackObservation history window.

    Args:
        history: Sequence of TrackObservation instances ordered from oldest to newest.
        window_seconds: Time horizon in seconds to look back from the newest frame.
        low_aspect_threshold: Aspect ratio threshold below which posture is considered low.
        low_angle_threshold_deg: Torso orientation angle below which posture is horizontal.

    Returns:
        TemporalFeatures describing motion dynamics over the specified window.

    Raises:
        ValueError: If history is empty or observations are not ordered monotonically.
        TypeError: If elements in history are not TrackObservation instances.
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
                f"out-of-order timestamp in history at index {i}: "
                f"{history[i].timestamp!r} < {history[i - 1].timestamp!r}"
            )

    t_newest = history[-1].timestamp
    t_cutoff = max(0.0, t_newest - window_seconds)

    # Slice history within window
    window_obs = [obs for obs in history if obs.timestamp >= t_cutoff]
    if not window_obs:
        window_obs = [history[-1]]

    # Extract geometry for each frame in window
    timestamped_geoms: list[tuple[float, PoseGeometryFeatures]] = [
        (obs.timestamp, extract_geometry_features(obs)) for obs in window_obs
    ]

    init_t, init_geom = timestamped_geoms[0]
    curr_t, curr_geom = timestamped_geoms[-1]

    dt = max(0.0, curr_t - init_t)
    ref_h = max(init_geom.bbox_height, 1e-6)

    # Vertical displacement (positive = downward in image coordinates)
    vert_disp = curr_geom.body_center[1] - init_geom.body_center[1]
    norm_vert_disp = vert_disp / ref_h

    # Average vertical velocity (pixels/s and heights/s)
    if dt > 1e-5:
        vert_vel = vert_disp / dt
        norm_vert_vel = norm_vert_disp / dt
    else:
        vert_vel = 0.0
        norm_vert_vel = 0.0

    # Instantaneous peak downward velocity across pairs in window
    peak_vel = 0.0
    for i in range(1, len(timestamped_geoms)):
        pair_dt = max(1e-4, timestamped_geoms[i][0] - timestamped_geoms[i - 1][0])
        pair_dy = (
            timestamped_geoms[i][1].body_center[1] - timestamped_geoms[i - 1][1].body_center[1]
        )
        instant_vel = pair_dy / pair_dt
        if instant_vel > peak_vel:
            peak_vel = instant_vel

    norm_peak_vel = peak_vel / ref_h

    # Geometry changes
    h_change_ratio = (curr_geom.bbox_height - init_geom.bbox_height) / ref_h
    aspect_ratio_change = curr_geom.aspect_ratio - init_geom.aspect_ratio
    torso_angle_change = curr_geom.torso_angle_deg - init_geom.torso_angle_deg

    # Low posture duration and stability
    low_posture_dur = _compute_low_posture_duration(
        timestamped_geoms,
        aspect_threshold=low_aspect_threshold,
        angle_threshold_deg=low_angle_threshold_deg,
    )

    stability = _compute_post_descent_stability(
        timestamped_geoms,
        aspect_threshold=low_aspect_threshold,
        angle_threshold_deg=low_angle_threshold_deg,
    )

    # Average keypoint confidence across all observations in window
    avg_conf = sum(geom.keypoint_confidence_mean for _, geom in timestamped_geoms) / len(
        timestamped_geoms
    )

    return TemporalFeatures(
        current_geometry=curr_geom,
        initial_geometry=init_geom,
        history_duration_seconds=dt,
        observation_count=len(window_obs),
        vertical_displacement=vert_disp,
        normalized_vertical_displacement=norm_vert_disp,
        vertical_velocity=vert_vel,
        normalized_vertical_velocity=norm_vert_vel,
        peak_vertical_velocity=peak_vel,
        normalized_peak_vertical_velocity=norm_peak_vel,
        bbox_height_change_ratio=h_change_ratio,
        aspect_ratio_change=aspect_ratio_change,
        torso_angle_change_deg=torso_angle_change,
        low_posture_duration_seconds=low_posture_dur,
        post_descent_motion_stability=stability,
        average_keypoint_confidence=avg_conf,
    )
