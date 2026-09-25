"""Configuration parameters for the fall detection state machine v3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class FallStateMachineConfigV3:
    """Configurable thresholds and timing windows for fall state progression v3."""

    # Feature extraction window
    feature_window_sec: float = 1.0

    # Scale-normalized descent triggers (in standing-heights/sec)
    descent_velocity_threshold: float = 0.35
    peak_descent_velocity_threshold: float = 0.70
    descent_aspect_ratio_drop: float = -0.25

    # Low/fallen posture criteria
    fallen_aspect_ratio_max: float = 1.10
    fallen_torso_angle_max_deg: float = 40.0
    min_down_confirming_frames: int = 3

    # Timeouts and persistence durations
    descent_candidate_timeout_sec: float = 1.5
    down_confirmation_sec: float = 0.6

    # Recovery criteria
    recovery_aspect_ratio_min: float = 1.30
    recovery_torso_angle_min_deg: float = 55.0
    recovery_cooldown_sec: float = 5.0

    # Learned classifier integration
    use_learned_classifier: bool = True
    classifier_trigger_threshold: float = 0.40
    classifier_confirmation_threshold: float = 0.45
    classifier_veto_threshold: float = 0.35

    # V3 new fields
    feature_schema_version: str = "3.0.0"
    feature_dim: int = 24
    enable_track_stitching: bool = True
    stitch_max_gap_frames: int = 15
    stitch_spatial_threshold: float = 50.0
    stitch_keypoint_similarity_threshold: float = 0.6
    use_angular_velocity: bool = True
    angular_velocity_descent_threshold: float = 30.0
    enable_camera_normalization: bool = False
    camera_normalization_method: str = "floor_plane"

    @classmethod
    def from_yaml(cls, path: str | Path) -> FallStateMachineConfigV3:
        """Load configuration from a YAML file (e.g. config/fall_detection_v3.yaml)."""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        engine_cfg = data.get("fall_engine_v3", {})
        classifier_cfg = data.get("learned_classifier", {})
        tracker_cfg = data.get("tracker_v3", {})

        return cls(
            feature_window_sec=float(engine_cfg.get("feature_window_sec", 1.0)),
            descent_velocity_threshold=float(engine_cfg.get("descent_velocity_threshold", 0.35)),
            peak_descent_velocity_threshold=float(
                engine_cfg.get("peak_descent_velocity_threshold", 0.70)
            ),
            descent_aspect_ratio_drop=float(engine_cfg.get("descent_aspect_ratio_drop", -0.25)),
            fallen_aspect_ratio_max=float(engine_cfg.get("fallen_aspect_ratio_max", 1.10)),
            fallen_torso_angle_max_deg=float(engine_cfg.get("fallen_torso_angle_max_deg", 40.0)),
            min_down_confirming_frames=int(engine_cfg.get("min_down_confirming_frames", 3)),
            descent_candidate_timeout_sec=float(
                engine_cfg.get("descent_candidate_timeout_sec", 1.5)
            ),
            down_confirmation_sec=float(engine_cfg.get("down_confirmation_sec", 0.6)),
            recovery_aspect_ratio_min=float(engine_cfg.get("recovery_aspect_ratio_min", 1.30)),
            recovery_torso_angle_min_deg=float(
                engine_cfg.get("recovery_torso_angle_min_deg", 55.0)
            ),
            recovery_cooldown_sec=float(engine_cfg.get("recovery_cooldown_sec", 5.0)),
            use_learned_classifier=bool(classifier_cfg.get("enabled", True)),
            classifier_trigger_threshold=float(classifier_cfg.get("trigger_threshold", 0.40)),
            classifier_confirmation_threshold=float(
                classifier_cfg.get("confirmation_threshold", 0.45)
            ),
            classifier_veto_threshold=float(classifier_cfg.get("veto_threshold", 0.35)),
            feature_schema_version=str(engine_cfg.get("feature_schema_version", "3.0.0")),
            feature_dim=int(engine_cfg.get("feature_dim", 24)),
            enable_track_stitching=bool(tracker_cfg.get("enable_track_stitching", True)),
            stitch_max_gap_frames=int(tracker_cfg.get("stitch_max_gap_frames", 15)),
            stitch_spatial_threshold=float(tracker_cfg.get("stitch_spatial_threshold", 50.0)),
            stitch_keypoint_similarity_threshold=float(
                tracker_cfg.get("stitch_keypoint_similarity_threshold", 0.6)
            ),
        )
