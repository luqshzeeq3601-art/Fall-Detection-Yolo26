"""Scale-normalized and body-referenced pose features (Phase 11.5 v3)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

_NOSE = 0
_LEFT_EYE = 1
_RIGHT_EYE = 2
_LEFT_EAR = 3
_RIGHT_EAR = 4
_LEFT_SHOULDER = 5
_RIGHT_SHOULDER = 6
_LEFT_ELBOW = 7
_RIGHT_ELBOW = 8
_LEFT_WRIST = 9
_RIGHT_WRIST = 10
_LEFT_HIP = 11
_RIGHT_HIP = 12
_LEFT_KNEE = 13
_RIGHT_KNEE = 14
_LEFT_ANKLE = 15
_RIGHT_ANKLE = 16


@dataclass(frozen=True)
class PoseGeometryFeaturesV3:
    bbox_width: float
    bbox_height: float
    bbox_diagonal: float
    aspect_ratio: float
    shoulder_midpoint: tuple[float, float] | None
    hip_midpoint: tuple[float, float] | None
    head_point: tuple[float, float] | None
    torso_vector: tuple[float, float] | None
    torso_angle_deg: float
    body_center: tuple[float, float]
    hip_height_ratio: float
    keypoint_confidence_mean: float
    keypoints_present_count: int
    pelvis_center: tuple[float, float] | None
    torso_center: tuple[float, float] | None
    normalized_head_height: float | None
    shoulder_width_ratio: float
    hip_width_ratio: float
    body_compactness: float
    keypoint_missing_mask: tuple[bool, ...]
    low_confidence_keypoint_count: int
    symmetry_score: float


@dataclass(frozen=True)
class TemporalFeaturesV3:
    current_geometry: PoseGeometryFeaturesV3
    initial_geometry: PoseGeometryFeaturesV3
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
    centroid_acceleration: float
    angular_velocity_deg_per_sec: float
    angular_acceleration: float
    floor_proximity_ratio: float
    cumulative_descent_distance: float
    velocity_direction_angle: float
    track_age_seconds: float
    track_gap_count: int
    max_gap_duration_seconds: float
    keypoint_availability_rate: float
    feature_vector: tuple[float, ...]


def _midpoint_or_single(kpt_a: Keypoint, kpt_b: Keypoint) -> tuple[float, float] | None:
    a_valid = kpt_a.present and kpt_a.x is not None and kpt_a.y is not None
    b_valid = kpt_b.present and kpt_b.x is not None and kpt_b.y is not None

    if a_valid and b_valid:
        assert kpt_a.x is not None and kpt_a.y is not None
        assert kpt_b.x is not None and kpt_b.y is not None
        return ((kpt_a.x + kpt_b.x) / 2.0, (kpt_a.y + kpt_b.y) / 2.0)
    if a_valid:
        assert kpt_a.x is not None and kpt_a.y is not None
        return (kpt_a.x, kpt_a.y)
    if b_valid:
        assert kpt_b.x is not None and kpt_b.y is not None
        return (kpt_b.x, kpt_b.y)
    return None

def _distance(kpt_a: Keypoint, kpt_b: Keypoint) -> float:
    a_valid = kpt_a.present and kpt_a.x is not None and kpt_a.y is not None
    b_valid = kpt_b.present and kpt_b.x is not None and kpt_b.y is not None
    if a_valid and b_valid:
        return math.sqrt((kpt_a.x - kpt_b.x)**2 + (kpt_a.y - kpt_b.y)**2) # type: ignore
    return 0.0

def extract_geometry_features_v3(observation: Any) -> PoseGeometryFeaturesV3:
    if not isinstance(observation, TrackObservation):
        raise TypeError(f"observation must be a TrackObservation, got {type(observation).__name__}")

    x1, y1, x2, y2 = observation.bbox_xyxy
    bbox_w = max(0.0, x2 - x1)
    bbox_h = max(0.0, y2 - y1)
    bbox_diag = math.sqrt(bbox_w * bbox_w + bbox_h * bbox_h)
    aspect_ratio = bbox_h / max(bbox_w, 1e-6)

    kpts = observation.keypoints
    shoulder_mid = _midpoint_or_single(kpts[_LEFT_SHOULDER], kpts[_RIGHT_SHOULDER])
    hip_mid = _midpoint_or_single(kpts[_LEFT_HIP], kpts[_RIGHT_HIP])

    head_kpt = kpts[_NOSE]
    if head_kpt.present and head_kpt.x is not None and head_kpt.y is not None:
        head_pt: tuple[float, float] | None = (head_kpt.x, head_kpt.y)
    else:
        head_pt = _midpoint_or_single(kpts[_LEFT_EYE], kpts[_RIGHT_EYE])

    torso_vec: tuple[float, float] | None = None
    if shoulder_mid is not None and hip_mid is not None:
        torso_vec = (shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1])
        dx, dy = abs(torso_vec[0]), abs(torso_vec[1])
        torso_angle = 90.0 if (dx == 0.0 and dy == 0.0) else math.degrees(math.atan2(dy, dx))
    elif head_pt is not None and hip_mid is not None:
        torso_vec = (head_pt[0] - hip_mid[0], head_pt[1] - hip_mid[1])
        dx, dy = abs(torso_vec[0]), abs(torso_vec[1])
        torso_angle = 90.0 if (dx == 0.0 and dy == 0.0) else math.degrees(math.atan2(dy, dx))
    else:
        if aspect_ratio >= 1.6:
            torso_angle = 85.0
        elif aspect_ratio <= 0.6:
            torso_angle = 15.0
        else:
            torso_angle = math.degrees(math.atan2(bbox_h, max(bbox_w, 1e-6)))

    if hip_mid is not None:
        body_center = hip_mid
        hip_h_ratio = (hip_mid[1] - y1) / max(bbox_h, 1e-6)
    else:
        body_center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        hip_h_ratio = 0.5

    present_kpts = [k for k in kpts if k.present and k.x is not None and k.y is not None]
    present_count = len(present_kpts)
    conf_mean = sum(k.confidence for k in present_kpts) / present_count if present_count > 0 else 0.0

    # V3 features
    ref_h = max(bbox_h, 1e-6)

    pelvis_center = None
    if hip_mid is not None:
        pelvis_center = ((hip_mid[0] - x1) / max(bbox_w, 1e-6), (hip_mid[1] - y1) / ref_h)

    torso_center = None
    if hip_mid is not None and shoulder_mid is not None:
        tx = (hip_mid[0] + shoulder_mid[0]) / 2.0
        ty = (hip_mid[1] + shoulder_mid[1]) / 2.0
        torso_center = ((tx - x1) / max(bbox_w, 1e-6), (ty - y1) / ref_h)

    normalized_head_height = None
    if head_pt is not None:
        normalized_head_height = (head_pt[1] - y1) / ref_h

    shoulder_width_ratio = _distance(kpts[_LEFT_SHOULDER], kpts[_RIGHT_SHOULDER]) / ref_h
    hip_width_ratio = _distance(kpts[_LEFT_HIP], kpts[_RIGHT_HIP]) / ref_h
    body_compactness = (bbox_w * bbox_h) / (ref_h * ref_h)

    missing_mask = tuple(not (k.present and k.x is not None and k.y is not None) for k in kpts)
    low_conf_count = sum(1 for k in kpts if (k.present and k.confidence < 0.3) or not k.present)

    # Symmetry score (left-right pairs)
    pairs = [(_LEFT_EYE, _RIGHT_EYE), (_LEFT_EAR, _RIGHT_EAR), (_LEFT_SHOULDER, _RIGHT_SHOULDER),
             (_LEFT_ELBOW, _RIGHT_ELBOW), (_LEFT_WRIST, _RIGHT_WRIST), (_LEFT_HIP, _RIGHT_HIP),
             (_LEFT_KNEE, _RIGHT_KNEE), (_LEFT_ANKLE, _RIGHT_ANKLE)]
    sym_dists = []
    for l, r in pairs:
        lk, rk = kpts[l], kpts[r]
        if lk.present and rk.present and lk.x is not None and rk.x is not None and lk.y is not None and rk.y is not None:
            # Distance from body center X to left and right should be similar
            dl = abs(lk.x - body_center[0])
            dr = abs(rk.x - body_center[0])
            diff = abs(dl - dr) / max(dl + dr, 1e-6)
            sym_dists.append(max(0.0, 1.0 - diff))
    symmetry_score = sum(sym_dists) / len(sym_dists) if sym_dists else 0.5

    return PoseGeometryFeaturesV3(
        bbox_width=bbox_w,
        bbox_height=bbox_h,
        bbox_diagonal=bbox_diag,
        aspect_ratio=aspect_ratio,
        shoulder_midpoint=shoulder_mid,
        hip_midpoint=hip_mid,
        head_point=head_pt,
        torso_vector=torso_vec,
        torso_angle_deg=torso_angle,
        body_center=body_center,
        hip_height_ratio=hip_h_ratio,
        keypoint_confidence_mean=conf_mean,
        keypoints_present_count=present_count,
        pelvis_center=pelvis_center,
        torso_center=torso_center,
        normalized_head_height=normalized_head_height,
        shoulder_width_ratio=shoulder_width_ratio,
        hip_width_ratio=hip_width_ratio,
        body_compactness=body_compactness,
        keypoint_missing_mask=missing_mask,
        low_confidence_keypoint_count=low_conf_count,
        symmetry_score=symmetry_score,
    )


def extract_temporal_features_v3(
    history: Sequence[Any],
    *,
    window_seconds: float = 1.2,
    low_aspect_threshold: float = 0.95,
    low_angle_threshold_deg: float = 45.0,
) -> TemporalFeaturesV3:
    if not history:
        raise ValueError("history sequence must not be empty")

    t_newest = history[-1].timestamp
    t_cutoff = max(0.0, t_newest - window_seconds)

    all_geoms = [extract_geometry_features_v3(obs) for obs in history]

    upright_heights = [g.bbox_height for g in all_geoms if g.aspect_ratio >= 1.1]
    ref_h = max(upright_heights) if upright_heights else max(g.bbox_height for g in all_geoms)
    ref_h = max(ref_h, 30.0)

    upright_aspects = [g.aspect_ratio for g in all_geoms if g.aspect_ratio >= 1.1]
    ref_aspect = upright_aspects[0] if upright_aspects else all_geoms[0].aspect_ratio
    ref_aspect = max(ref_aspect, 0.4)

    window_tuples = [(obs.timestamp, g) for obs, g in zip(history, all_geoms) if obs.timestamp >= t_cutoff]
    if not window_tuples:
        window_tuples = [(history[-1].timestamp, all_geoms[-1])]

    init_t, init_geom = window_tuples[0]
    curr_t, curr_geom = window_tuples[-1]
    dt = max(0.0, curr_t - init_t)

    vert_disp = curr_geom.body_center[1] - init_geom.body_center[1]
    norm_disp = vert_disp / ref_h

    vert_vel = vert_disp / dt if dt > 1e-5 else 0.0
    scale_norm_vel = norm_disp / dt if dt > 1e-5 else 0.0

    peak_vel = 0.0
    for i in range(1, len(window_tuples)):
        p_dt = max(1e-4, window_tuples[i][0] - window_tuples[i - 1][0])
        p_dy = window_tuples[i][1].body_center[1] - window_tuples[i - 1][1].body_center[1]
        if p_dy / p_dt > peak_vel:
            peak_vel = p_dy / p_dt

    scale_norm_peak_vel = peak_vel / ref_h
    h_change_ratio = (curr_geom.bbox_height - ref_h) / ref_h
    aspect_rel_change = (curr_geom.aspect_ratio - ref_aspect) / ref_aspect
    torso_angle_change = curr_geom.torso_angle_deg - init_geom.torso_angle_deg

    low_dur = 0.0
    t_start = curr_t
    for t, geom in reversed(window_tuples):
        if geom.aspect_ratio <= low_aspect_threshold or geom.torso_angle_deg <= low_angle_threshold_deg:
            t_start = t
        else:
            break
    low_dur = max(0.0, curr_t - t_start)

    stability = 0.0
    low_frames = [(t, g) for t, g in window_tuples if g.aspect_ratio <= low_aspect_threshold or g.torso_angle_deg <= low_angle_threshold_deg]
    if len(low_frames) >= 2:
        speeds = []
        for i in range(1, len(low_frames)):
            p_dt = max(1e-4, low_frames[i][0] - low_frames[i - 1][0])
            dy = low_frames[i][1].body_center[1] - low_frames[i - 1][1].body_center[1]
            dx = low_frames[i][1].body_center[0] - low_frames[i - 1][1].body_center[0]
            speeds.append(math.sqrt(dx*dx + dy*dy) / p_dt)
        mean_s = sum(speeds) / len(speeds)
        stability = math.sqrt(sum((s - mean_s)**2 for s in speeds) / len(speeds))

    avg_conf = sum(g.keypoint_confidence_mean for _, g in window_tuples) / len(window_tuples)

    # V3 Temporal Features
    velocities_y = []
    velocities_x = []
    angular_velocities = []
    for i in range(1, len(window_tuples)):
        dt_i = max(1e-4, window_tuples[i][0] - window_tuples[i-1][0])
        dy_i = window_tuples[i][1].body_center[1] - window_tuples[i-1][1].body_center[1]
        dx_i = window_tuples[i][1].body_center[0] - window_tuples[i-1][1].body_center[0]
        dtheta_i = window_tuples[i][1].torso_angle_deg - window_tuples[i-1][1].torso_angle_deg
        velocities_y.append(dy_i / dt_i)
        velocities_x.append(dx_i / dt_i)
        angular_velocities.append(dtheta_i / dt_i)
    
    if len(velocities_y) >= 2:
        accels_y = [(velocities_y[i] - velocities_y[i-1]) / max(1e-4, window_tuples[i+1][0] - window_tuples[i][0]) for i in range(1, len(velocities_y))]
        centroid_acceleration = (sum(accels_y) / len(accels_y)) / ref_h
        
        accels_theta = [(angular_velocities[i] - angular_velocities[i-1]) / max(1e-4, window_tuples[i+1][0] - window_tuples[i][0]) for i in range(1, len(angular_velocities))]
        angular_acceleration = sum(accels_theta) / len(accels_theta)
    else:
        centroid_acceleration = 0.0
        angular_acceleration = 0.0

    angular_velocity_deg_per_sec = angular_velocities[-1] if angular_velocities else 0.0

    # floor_proximity_ratio
    max_y = max(curr_geom.body_center[1], curr_geom.head_point[1] if curr_geom.head_point else 0.0)
    for obs in history:
        for k in obs.keypoints:
            if k.present and k.y is not None:
                max_y = max(max_y, k.y)
    
    image_h = curr_geom.bbox_height * 2.0  # Approximation since we don't have image height
    if hasattr(history[-1], 'image_height') and history[-1].image_height:
        image_h = history[-1].image_height
    floor_proximity_ratio = (image_h - max_y) / max(image_h, 1e-6)

    cumulative_descent = 0.0
    for i in range(1, len(window_tuples)):
        dy_i = window_tuples[i][1].body_center[1] - window_tuples[i-1][1].body_center[1]
        if dy_i > 0:
            cumulative_descent += dy_i
    cumulative_descent_distance = cumulative_descent / ref_h

    vx = sum(velocities_x) / len(velocities_x) if velocities_x else 0.0
    vy = sum(velocities_y) / len(velocities_y) if velocities_y else 0.0
    velocity_direction_angle = math.degrees(math.atan2(vy, vx))

    track_age_seconds = history[-1].timestamp - history[0].timestamp

    track_gap_count = 0
    max_gap = 0.0
    for i in range(1, len(history)):
        gap = history[i].timestamp - history[i-1].timestamp
        if gap > 0.1: # Threshold for gap
            track_gap_count += 1
            max_gap = max(max_gap, gap)
    max_gap_duration_seconds = max_gap

    usable_frames = sum(1 for g in all_geoms if g.keypoints_present_count >= 8)
    keypoint_availability_rate = usable_frames / len(all_geoms)

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
        float(centroid_acceleration),
        float(angular_velocity_deg_per_sec),
        float(angular_acceleration),
        float(floor_proximity_ratio),
        float(cumulative_descent_distance),
        float(velocity_direction_angle),
        float(track_age_seconds),
        float(track_gap_count),
        float(max_gap_duration_seconds),
        float(keypoint_availability_rate),
        float(curr_geom.shoulder_width_ratio),
        float(curr_geom.body_compactness),
    )

    return TemporalFeaturesV3(
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
        centroid_acceleration=centroid_acceleration,
        angular_velocity_deg_per_sec=angular_velocity_deg_per_sec,
        angular_acceleration=angular_acceleration,
        floor_proximity_ratio=floor_proximity_ratio,
        cumulative_descent_distance=cumulative_descent_distance,
        velocity_direction_angle=velocity_direction_angle,
        track_age_seconds=track_age_seconds,
        track_gap_count=track_gap_count,
        max_gap_duration_seconds=max_gap_duration_seconds,
        keypoint_availability_rate=keypoint_availability_rate,
        feature_vector=feat_vec,
    )
