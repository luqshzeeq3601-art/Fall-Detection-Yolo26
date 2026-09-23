"""Configuration parameters for the fall detection state machine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FallStateMachineConfig:
    """Configurable thresholds and timing windows for fall state progression.

    All parameters have safe engineering defaults that can be calibrated
    on the development split without requiring code changes.
    """

    # Feature extraction window
    feature_window_sec: float = 0.5

    # Descent candidate triggers
    descent_velocity_threshold: float = 0.5  # Mean normalized downward velocity (heights/s)
    peak_descent_velocity_threshold: float = 1.0  # Peak instantaneous downward velocity (heights/s)
    descent_aspect_ratio_drop: float = -0.5  # Aspect ratio drop during candidate window

    # Low/fallen posture criteria
    fallen_aspect_ratio_max: float = 1.0  # Max aspect ratio (H/W) to be considered down/fallen
    fallen_torso_angle_max_deg: float = 40.0  # Max torso angle from horizontal to be down
    min_down_confirming_frames: int = 2  # Multi-frame minimum down frames to confirm candidate

    # Timeouts and persistence durations
    descent_candidate_timeout_sec: float = 1.0  # Candidate expires if down not reached
    down_confirmation_sec: float = 1.0  # Time down posture must persist to confirm fall

    # Recovery criteria
    recovery_aspect_ratio_min: float = 1.4  # Aspect ratio indicating upright standing/sitting
    recovery_torso_angle_min_deg: float = 50.0  # Torso angle indicating upright recovery
    recovery_cooldown_sec: float = 5.0  # Cooldown duration in RECOVERY before returning to NORMAL
