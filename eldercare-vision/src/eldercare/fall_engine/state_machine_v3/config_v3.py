"""Configuration parameters for the fall detection state machine v3."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FallStateMachineConfigV3:
    """Configurable thresholds and timing windows for fall state progression v3."""

    # Feature extraction window
    feature_window_sec: float = 0.6

    # Scale-normalized descent triggers (in standing-heights/sec)
    descent_velocity_threshold: float = 0.40
    peak_descent_velocity_threshold: float = 0.80
    descent_aspect_ratio_drop: float = -0.30

    # Low/fallen posture criteria
    fallen_aspect_ratio_max: float = 1.05
    fallen_torso_angle_max_deg: float = 45.0
    min_down_confirming_frames: int = 2

    # Timeouts and persistence durations
    descent_candidate_timeout_sec: float = 1.2
    down_confirmation_sec: float = 0.8

    # Recovery criteria
    recovery_aspect_ratio_min: float = 1.35
    recovery_torso_angle_min_deg: float = 50.0
    recovery_cooldown_sec: float = 5.0

    # Learned classifier integration
    use_learned_classifier: bool = True
    classifier_trigger_threshold: float = 0.45
    classifier_confirmation_threshold: float = 0.50
    
    # V3 new fields
    feature_schema_version: str = '3.0.0'
    feature_dim: int = 24
    enable_track_stitching: bool = True
    stitch_max_gap_frames: int = 15
    stitch_spatial_threshold: float = 50.0
    stitch_keypoint_similarity_threshold: float = 0.6
    use_angular_velocity: bool = True
    angular_velocity_descent_threshold: float = 30.0
    enable_camera_normalization: bool = False
    camera_normalization_method: str = 'floor_plane'
