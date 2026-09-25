# ruff: noqa: E501
"""Camera Perspective & Height Invariance Normalization Module (Phase 11.7 P11.7-013).

Provides perspective rectification, gravity-aligned coordinate transformation,
ground-plane distance compensation, and auto-calibration for multi-camera invariance.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraNormalizationConfig:
    """Configuration for camera orientation and height invariance."""

    enabled: bool = True
    camera_height_meters: float = 2.4       # Mounting height (meters)
    camera_pitch_deg: float = 25.0          # Downward pitch from horizontal (degrees)
    camera_roll_deg: float = 0.0            # Roll angle (degrees)
    focal_length_px: float = 500.0          # Focal length in pixels
    auto_calibrate_from_tracks: bool = True # Automatically refine pitch from upright tracks
    nominal_person_height_m: float = 1.70   # Standard human height reference


@dataclass(frozen=True)
class PerspectiveRectificationResult:
    """Rectification summary for a tracked observation or feature set."""

    gravity_aligned_peak_velocity: float
    gravity_aligned_vertical_displacement: float
    rectified_torso_angle_deg: float
    estimated_distance_meters: float
    scale_factor: float


class CameraPerspectiveNormalizer:
    """Normalizes 2D keypoints and motion dynamics against camera perspective and mounting height."""

    def __init__(self, config: CameraNormalizationConfig | None = None) -> None:
        self.config = config or CameraNormalizationConfig()
        self._rotation_matrix = self._compute_rotation_matrix(
            pitch_deg=self.config.camera_pitch_deg,
            roll_deg=self.config.camera_roll_deg,
        )

    def _compute_rotation_matrix(self, pitch_deg: float, roll_deg: float) -> np.ndarray:
        """Compute 3D rotation matrix for camera pitch and roll."""
        p_rad = math.radians(pitch_deg)
        r_rad = math.radians(roll_deg)

        # Pitch rotation around X-axis (tilting down looking +Z)
        r_pitch = np.array([
            [1.0, 0.0, 0.0],
            [0.0, math.cos(p_rad), -math.sin(p_rad)],
            [0.0, math.sin(p_rad), math.cos(p_rad)],
        ], dtype=np.float32)

        # Roll rotation around Z-axis
        r_roll = np.array([
            [math.cos(r_rad), -math.sin(r_rad), 0.0],
            [math.sin(r_rad), math.cos(r_rad), 0.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)

        return r_roll @ r_pitch

    def estimate_distance_to_person(
        self,
        bbox_height_px: float,
        foot_y_px: float,
        image_height_px: float = 480.0,
    ) -> float:
        """Estimate 3D ground distance to person from camera mounting height and bounding box."""
        if not self.config.enabled or bbox_height_px <= 1.0:
            return 3.0  # Default nominal distance

        # Method 1: Apparent size scaling (f * H / h_px)
        f = self.config.focal_length_px
        h_real = self.config.nominal_person_height_m
        dist_size = (f * h_real) / max(1.0, bbox_height_px)

        # Method 2: Ground plane ray intersection
        cy = image_height_px / 2.0
        pitch_rad = math.radians(self.config.camera_pitch_deg)
        ray_angle = math.atan2(foot_y_px - cy, f) + pitch_rad
        if ray_angle > 0.05:
            dist_ground = self.config.camera_height_meters / math.tan(ray_angle)
        else:
            dist_ground = dist_size

        # Robust blended estimate
        est_dist = float(0.6 * dist_size + 0.4 * dist_ground)
        return float(np.clip(est_dist, 0.5, 20.0))

    def rectify_vertical_velocity(
        self,
        vy_normalized: float,
        distance_meters: float | None = None,
    ) -> float:
        """Rectify 2D vertical velocity (standing-heights/sec) to true gravity-aligned descent velocity."""
        if not self.config.enabled:
            return float(vy_normalized)

        pitch_rad = math.radians(self.config.camera_pitch_deg)
        # When camera is tilted down by pitch theta, a vertical descent in world space
        # projects onto the image plane with foreshortening factor cos(theta).
        # Rectifying requires dividing by cos(theta) (or scaling by sec(theta)).
        cos_p = max(0.2, math.cos(pitch_rad))
        rectified_vy = float(vy_normalized / cos_p)
        return rectified_vy

    def rectify_torso_angle(
        self,
        torso_angle_deg: float,
        aspect_ratio: float = 1.0,
    ) -> float:
        """Compensate torso angle (degrees) for camera downward pitch perspective distortion."""
        if not self.config.enabled or abs(self.config.camera_pitch_deg) < 1.0:
            return float(torso_angle_deg)

        pitch_deg = self.config.camera_pitch_deg
        # An upright person (90 deg) tilted by camera pitch theta appears slightly compressed
        # in aspect ratio, but true angle with respect to floor normal is:
        # phi_world = atan(tan(phi_2d) / cos(theta_pitch))
        phi_rad = math.radians(max(1.0, min(89.0, torso_angle_deg)))
        pitch_rad = math.radians(pitch_deg)
        cos_p = max(0.2, math.cos(pitch_rad))

        tan_world = math.tan(phi_rad) / cos_p
        world_angle_deg = math.degrees(math.atan(tan_world))

        return float(np.clip(world_angle_deg, 0.0, 90.0))

    def rectify_keypoints(
        self,
        keypoints: tuple[Keypoint, ...],
        image_width_px: float = 640.0,
        image_height_px: float = 480.0,
    ) -> tuple[Keypoint, ...]:
        """Project 2D keypoints into gravity-rectified perspective plane."""
        if not self.config.enabled or abs(self.config.camera_pitch_deg) < 1.0:
            return keypoints

        cx = image_width_px / 2.0
        cy = image_height_px / 2.0
        f = self.config.focal_length_px
        p_rad = math.radians(self.config.camera_pitch_deg)
        cos_p = math.cos(p_rad)
        sin_p = math.sin(p_rad)

        rectified_kpts = []
        for k in keypoints:
            if not k.present or k.x is None or k.y is None:
                rectified_kpts.append(k)
                continue

            # Normalized camera ray
            x_norm = (k.x - cx) / f
            y_norm = (k.y - cy) / f

            # De-rotate pitch around X-axis
            y_rect = y_norm * cos_p + sin_p
            z_rect = -y_norm * sin_p + cos_p

            if abs(z_rect) > 1e-4:
                x_proj = cx + f * (x_norm / z_rect)
                y_proj = cy + f * (y_rect / z_rect)
            else:
                x_proj, y_proj = k.x, k.y

            rectified_kpts.append(
                Keypoint(
                    present=True,
                    x=float(x_proj),
                    y=float(y_proj),
                    confidence=float(k.confidence),
                )
            )

        return tuple(rectified_kpts)

    def auto_calibrate_pitch_from_upright_tracks(
        self,
        upright_observations: Sequence[TrackObservation],
    ) -> float:
        """Estimate camera pitch angle from statistics of upright human tracks."""
        if not upright_observations:
            return float(self.config.camera_pitch_deg)

        # In upright standing postures, human aspect ratio is nominally ~1.8 - 2.2.
        # Downward pitch foreshortens bounding box height according to aspect_observed = aspect_true * cos(pitch).
        aspect_ratios = []
        for obs in upright_observations:
            w = obs.bbox_xyxy[2] - obs.bbox_xyxy[0]
            h = obs.bbox_xyxy[3] - obs.bbox_xyxy[1]
            if h > 30.0 and w > 10.0:
                aspect_ratios.append(h / w)

        if not aspect_ratios:
            return float(self.config.camera_pitch_deg)

        median_aspect = float(np.median(aspect_ratios))
        nominal_upright_aspect = 2.0
        ratio = np.clip(median_aspect / nominal_upright_aspect, 0.4, 1.0)
        estimated_pitch = math.degrees(math.acos(ratio))

        return float(np.clip(estimated_pitch, 0.0, 60.0))
