"""Single-frame pose geometry feature extraction (P4-002).

Pure, deterministic geometry extraction from a TrackObservation per AI_SPEC.md §6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

_LEFT_SHOULDER = 5
_RIGHT_SHOULDER = 6
_LEFT_HIP = 11
_RIGHT_HIP = 12


@dataclass(frozen=True)
class PoseGeometryFeatures:
    """Extracted geometric features for one person observation at one time point.

    Attributes:
        bbox_width: Bounding box width in pixels.
        bbox_height: Bounding box height in pixels.
        aspect_ratio: Height / width ratio (height / max(width, 1e-6)).
        shoulder_midpoint: (x, y) coordinates of shoulder midpoint, or fallback.
        hip_midpoint: (x, y) coordinates of hip midpoint, or fallback.
        torso_vector: (dx, dy) vector pointing from hip midpoint to shoulder midpoint.
        torso_angle_deg: Torso orientation angle relative to horizontal in [0, 90] degrees
            (90 = vertical upright, 0 = horizontal flat).
        body_center: (x, y) coordinates of body center (hip midpoint or bbox center).
        keypoint_confidence_mean: Mean confidence of present keypoints in [0, 1].
        keypoints_present_count: Count of present keypoints out of 17.
    """

    bbox_width: float
    bbox_height: float
    aspect_ratio: float
    shoulder_midpoint: tuple[float, float] | None
    hip_midpoint: tuple[float, float] | None
    torso_vector: tuple[float, float] | None
    torso_angle_deg: float
    body_center: tuple[float, float]
    keypoint_confidence_mean: float
    keypoints_present_count: int


def _midpoint_or_single(
    kpt_a: Keypoint,
    kpt_b: Keypoint,
) -> tuple[float, float] | None:
    """Calculate midpoint of two keypoints, falling back to whichever is present."""
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


def extract_geometry_features(observation: Any) -> PoseGeometryFeatures:
    """Extract geometric posture features from a TrackObservation.

    Args:
        observation: A TrackObservation instance.

    Returns:
        PoseGeometryFeatures containing all geometry attributes.
    """
    if not isinstance(observation, TrackObservation):
        raise TypeError(f"observation must be a TrackObservation, got {type(observation).__name__}")

    x1, y1, x2, y2 = observation.bbox_xyxy
    bbox_w = max(0.0, x2 - x1)
    bbox_h = max(0.0, y2 - y1)
    aspect_ratio = bbox_h / max(bbox_w, 1e-6)

    kpts = observation.keypoints
    shoulder_mid = _midpoint_or_single(kpts[_LEFT_SHOULDER], kpts[_RIGHT_SHOULDER])
    hip_mid = _midpoint_or_single(kpts[_LEFT_HIP], kpts[_RIGHT_HIP])

    # Torso vector from hip midpoint to shoulder midpoint
    if shoulder_mid is not None and hip_mid is not None:
        torso_vec: tuple[float, float] | None = (
            shoulder_mid[0] - hip_mid[0],
            shoulder_mid[1] - hip_mid[1],
        )
        dx = abs(torso_vec[0])
        dy = abs(torso_vec[1])
        if dx == 0.0 and dy == 0.0:
            torso_angle = 90.0
        else:
            torso_angle = math.degrees(math.atan2(dy, dx))
    else:
        torso_vec = None
        # Fallback angle derived from bbox aspect ratio
        if aspect_ratio >= 1.5:
            torso_angle = 85.0
        elif aspect_ratio <= 0.6:
            torso_angle = 15.0
        else:
            torso_angle = math.degrees(math.atan2(bbox_h, max(bbox_w, 1e-6)))

    # Body center: hip midpoint fallback to bbox center
    if hip_mid is not None:
        body_center = hip_mid
    else:
        body_center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    # Keypoint statistics
    present_kpts = [k for k in kpts if k.present and k.x is not None and k.y is not None]
    present_count = len(present_kpts)
    if present_count > 0:
        conf_mean = sum(k.confidence for k in present_kpts) / present_count
    else:
        conf_mean = 0.0

    return PoseGeometryFeatures(
        bbox_width=bbox_w,
        bbox_height=bbox_h,
        aspect_ratio=aspect_ratio,
        shoulder_midpoint=shoulder_mid,
        hip_midpoint=hip_mid,
        torso_vector=torso_vec,
        torso_angle_deg=torso_angle,
        body_center=body_center,
        keypoint_confidence_mean=conf_mean,
        keypoints_present_count=present_count,
    )
