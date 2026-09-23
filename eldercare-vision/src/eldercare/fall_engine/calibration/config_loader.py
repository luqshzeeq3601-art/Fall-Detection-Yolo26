"""Configuration loader and schema validator for fall detection engine (P4-007)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig


def _as_float(value: Any, *, what: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a real number, got bool {value!r}")
    try:
        val = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be a real number, got {value!r}") from exc
    if not math.isfinite(val):
        raise ValueError(f"{what} must be finite, got {value!r}")
    return val


def _as_int(value: Any, *, what: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{what} must be an int, got bool {value!r}")
    try:
        val = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be an int, got {value!r}") from exc
    return val


def load_fall_detection_config(
    config_path: str | Path,
) -> tuple[FallStateMachineConfig, FallConfidenceConfig, CooldownConfig]:
    """Load and validate fall engine configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Tuple of (FallStateMachineConfig, FallConfidenceConfig, CooldownConfig).

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If YAML syntax is invalid or configuration parameters are invalid.
    """
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(path, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML configuration: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping, got {type(data).__name__}")

    # 1. Parse FallStateMachineConfig
    fe_data = data.get("fall_engine", {})
    if not isinstance(fe_data, dict):
        raise ValueError(f"'fall_engine' section must be a mapping, got {type(fe_data).__name__}")

    state_config = FallStateMachineConfig(
        feature_window_sec=_as_float(
            fe_data.get("feature_window_sec", 0.5), what="feature_window_sec"
        ),
        descent_velocity_threshold=_as_float(
            fe_data.get("descent_velocity_threshold", 0.5),
            what="descent_velocity_threshold",
        ),
        peak_descent_velocity_threshold=_as_float(
            fe_data.get("peak_descent_velocity_threshold", 1.0),
            what="peak_descent_velocity_threshold",
        ),
        descent_aspect_ratio_drop=_as_float(
            fe_data.get("descent_aspect_ratio_drop", -0.5),
            what="descent_aspect_ratio_drop",
        ),
        fallen_aspect_ratio_max=_as_float(
            fe_data.get("fallen_aspect_ratio_max", 1.0),
            what="fallen_aspect_ratio_max",
        ),
        fallen_torso_angle_max_deg=_as_float(
            fe_data.get("fallen_torso_angle_max_deg", 40.0),
            what="fallen_torso_angle_max_deg",
        ),
        min_down_confirming_frames=_as_int(
            fe_data.get("min_down_confirming_frames", 2),
            what="min_down_confirming_frames",
        ),
        descent_candidate_timeout_sec=_as_float(
            fe_data.get("descent_candidate_timeout_sec", 1.0),
            what="descent_candidate_timeout_sec",
        ),
        down_confirmation_sec=_as_float(
            fe_data.get("down_confirmation_sec", 1.0),
            what="down_confirmation_sec",
        ),
        recovery_aspect_ratio_min=_as_float(
            fe_data.get("recovery_aspect_ratio_min", 1.4),
            what="recovery_aspect_ratio_min",
        ),
        recovery_torso_angle_min_deg=_as_float(
            fe_data.get("recovery_torso_angle_min_deg", 50.0),
            what="recovery_torso_angle_min_deg",
        ),
        recovery_cooldown_sec=_as_float(
            fe_data.get("recovery_cooldown_sec", 5.0),
            what="recovery_cooldown_sec",
        ),
    )

    # 2. Parse FallConfidenceConfig
    conf_data = data.get("confidence", {})
    if not isinstance(conf_data, dict):
        raise ValueError(f"'confidence' section must be a mapping, got {type(conf_data).__name__}")

    w_motion = _as_float(conf_data.get("weight_motion", 0.35), what="weight_motion")
    w_posture = _as_float(conf_data.get("weight_posture", 0.35), what="weight_posture")
    w_persistence = _as_float(conf_data.get("weight_persistence", 0.30), what="weight_persistence")

    # Validate weights sum to approximately 1.0
    weight_sum = w_motion + w_posture + w_persistence
    if abs(weight_sum - 1.0) > 1e-4:
        raise ValueError(
            f"Confidence weights must sum to 1.0, got {weight_sum} "
            f"(motion={w_motion}, posture={w_posture}, persistence={w_persistence})"
        )

    confidence_config = FallConfidenceConfig(
        weight_motion=w_motion,
        weight_posture=w_posture,
        weight_persistence=w_persistence,
        missing_keypoint_penalty_weight=_as_float(
            conf_data.get("missing_keypoint_penalty_weight", 0.20),
            what="missing_keypoint_penalty_weight",
        ),
        unstable_track_penalty_weight=_as_float(
            conf_data.get("unstable_track_penalty_weight", 0.15),
            what="unstable_track_penalty_weight",
        ),
        min_confidence_to_confirm=_as_float(
            conf_data.get("min_confidence_to_confirm", 0.40),
            what="min_confidence_to_confirm",
        ),
        target_peak_velocity=_as_float(
            conf_data.get("target_peak_velocity", 1.5),
            what="target_peak_velocity",
        ),
        target_torso_angle_collapsed_deg=_as_float(
            conf_data.get("target_torso_angle_collapsed_deg", 20.0),
            what="target_torso_angle_collapsed_deg",
        ),
        target_aspect_ratio_collapsed=_as_float(
            conf_data.get("target_aspect_ratio_collapsed", 0.6),
            what="target_aspect_ratio_collapsed",
        ),
        target_down_confirmation_sec=_as_float(
            conf_data.get("target_down_confirmation_sec", 1.0),
            what="target_down_confirmation_sec",
        ),
        detector_model=str(conf_data.get("detector_model", "yolo26s-pose.pt")),
        tracker_name=str(conf_data.get("tracker_name", "bytetrack")),
        config_version=str(conf_data.get("config_version", "1.0.0")),
    )

    # 3. Parse CooldownConfig
    cd_data = data.get("cooldown", {})
    if not isinstance(cd_data, dict):
        raise ValueError(f"'cooldown' section must be a mapping, got {type(cd_data).__name__}")

    cooldown_config = CooldownConfig(
        incident_cooldown_sec=_as_float(
            cd_data.get("incident_cooldown_sec", 5.0), what="incident_cooldown_sec"
        ),
        camera_cooldown_sec=_as_float(
            cd_data.get("camera_cooldown_sec", 0.5), what="camera_cooldown_sec"
        ),
    )

    return state_config, confidence_config, cooldown_config
