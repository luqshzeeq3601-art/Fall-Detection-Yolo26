"""Explainable fall confidence score calculation and evidence breakdown (P4-004).

Implements confidence-aware logic per AI_SPEC.md §8 and evidence explainability
per AI_SPEC.md §10.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from eldercare.fall_engine.features.motion import TemporalFeatures
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class FallConfidenceConfig:
    """Configurable weights and penalties for composite fall confidence scoring."""

    # Component weights (must sum to 1.0)
    weight_motion: float = 0.35
    weight_posture: float = 0.35
    weight_persistence: float = 0.30

    # Penalty weights
    missing_keypoint_penalty_weight: float = 0.20
    unstable_track_penalty_weight: float = 0.15

    # Minimum composite confidence required to confirm a fall event
    min_confidence_to_confirm: float = 0.40

    # Normalization calibration targets
    target_peak_velocity: float = 1.5  # person heights/second
    target_torso_angle_collapsed_deg: float = 20.0
    target_aspect_ratio_collapsed: float = 0.6
    target_down_confirmation_sec: float = 1.0

    # Metadata & provenance
    detector_model: str = "yolo26s-pose.pt"
    tracker_name: str = "bytetrack"
    config_version: str = "1.0.0"


@dataclass(frozen=True)
class FallConfidenceBreakdown:
    """Explainable audit breakdown of evidence contributing to a fall detection."""

    composite_confidence: float
    motion_score: float
    posture_score: float
    persistence_score: float
    missing_keypoint_penalty: float
    unstable_track_penalty: float
    average_pose_confidence: float
    key_contributing_features: dict[str, float] = field(default_factory=dict)
    detector_model: str = "yolo26s-pose.pt"
    tracker_name: str = "bytetrack"
    config_version: str = "1.0.0"


def compute_fall_confidence(
    feats: TemporalFeatures,
    history: Sequence[TrackObservation],
    down_duration_seconds: float,
    config: FallConfidenceConfig | None = None,
    candidate_features: TemporalFeatures | None = None,
) -> FallConfidenceBreakdown:
    """Compute composite confidence score and granular evidence breakdown.

    Formula:
        Score = w_motion * S_motion
              + w_posture * S_posture
              + w_persistence * S_persistence
              - P_missing_keypoint
              - P_unstable_track

    Args:
        feats: Extracted temporal features for the current sliding window.
        history: Observation history for this track.
        down_duration_seconds: Duration person has been sustained in down posture.
        config: Confidence scoring configuration.
        candidate_features: Temporal features captured during initial descent candidate trigger.

    Returns:
        FallConfidenceBreakdown with explainable sub-scores, penalties, and composite confidence.
    """
    cfg = config or FallConfidenceConfig()

    # 1. Motion Score [0.0, 1.0]
    # Uses candidate descent features if provided, otherwise current window features
    motion_feats = candidate_features if candidate_features is not None else feats
    peak_vel = max(0.0, motion_feats.normalized_peak_vertical_velocity)
    motion_score = min(1.0, max(0.0, peak_vel / cfg.target_peak_velocity))

    # 2. Posture Score [0.0, 1.0]
    # Combines aspect ratio collapse and horizontal torso orientation
    curr_ar = feats.current_geometry.aspect_ratio
    curr_angle = feats.current_geometry.torso_angle_deg

    # Aspect score: 1.0 if AR <= target_aspect_ratio_collapsed, 0.0 if AR >= 1.8
    ar_span = max(0.1, 1.8 - cfg.target_aspect_ratio_collapsed)
    ar_score = min(1.0, max(0.0, (1.8 - curr_ar) / ar_span))

    # Angle score: 1.0 if angle <= target_torso_angle_collapsed_deg, 0.0 if angle >= 80 deg
    angle_span = max(1.0, 80.0 - cfg.target_torso_angle_collapsed_deg)
    angle_score = min(1.0, max(0.0, (80.0 - curr_angle) / angle_span))

    posture_score = 0.5 * ar_score + 0.5 * angle_score

    # 3. Persistence Score [0.0, 1.0]
    # Scales with how long the person has remained down
    pers_target = max(0.1, cfg.target_down_confirmation_sec)
    persistence_score = min(1.0, max(0.0, down_duration_seconds / pers_target))

    # 4. Missing Keypoint Penalty [0.0, missing_keypoint_penalty_weight]
    latest_obs = history[-1] if history else None
    if latest_obs is not None and latest_obs.keypoints:
        present_count = sum(
            1
            for k in latest_obs.keypoints
            if k.present and k.confidence >= 0.25 and k.x is not None and k.y is not None
        )
        total_kpts = len(latest_obs.keypoints)
        missing_fraction = max(0.0, 1.0 - (present_count / total_kpts))
    else:
        missing_fraction = 1.0

    missing_keypoint_penalty = cfg.missing_keypoint_penalty_weight * missing_fraction

    # 5. Unstable Track Penalty [0.0, unstable_track_penalty_weight]
    # Penalizes tracks with low detection confidence
    if latest_obs is not None:
        det_conf = latest_obs.detection_confidence
        det_deficit = max(0.0, 0.8 - det_conf) / 0.8
    else:
        det_deficit = 1.0
    unstable_track_penalty = cfg.unstable_track_penalty_weight * det_deficit

    # 6. Composite Score
    weighted_evidence = (
        cfg.weight_motion * motion_score
        + cfg.weight_posture * posture_score
        + cfg.weight_persistence * persistence_score
    )
    total_penalties = missing_keypoint_penalty + unstable_track_penalty
    composite = min(1.0, max(0.0, weighted_evidence - total_penalties))

    # Key contributing features dictionary for audit
    key_features = {
        "normalized_peak_vertical_velocity": feats.normalized_peak_vertical_velocity,
        "normalized_vertical_velocity": feats.normalized_vertical_velocity,
        "aspect_ratio": curr_ar,
        "torso_angle_deg": curr_angle,
        "down_duration_seconds": down_duration_seconds,
        "aspect_ratio_change": feats.aspect_ratio_change,
        "post_descent_motion_stability": feats.post_descent_motion_stability,
    }

    return FallConfidenceBreakdown(
        composite_confidence=round(composite, 4),
        motion_score=round(motion_score, 4),
        posture_score=round(posture_score, 4),
        persistence_score=round(persistence_score, 4),
        missing_keypoint_penalty=round(missing_keypoint_penalty, 4),
        unstable_track_penalty=round(unstable_track_penalty, 4),
        average_pose_confidence=round(feats.average_keypoint_confidence, 4),
        key_contributing_features=key_features,
        detector_model=cfg.detector_model,
        tracker_name=cfg.tracker_name,
        config_version=cfg.config_version,
    )
