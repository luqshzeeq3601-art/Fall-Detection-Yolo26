"""Enhanced single-frame pose geometry feature extraction (Phase 11.5 v2).

Provides scale-normalized posture geometry, multi-keypoint torso vector estimation,
and robust fallback calculations for occluded or ground-level postures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

_NOSE = 0
_LEFT_EYE = 1
_RIGHT_EYE = 2
_LEFT_SHOULDER = 5
_RIGHT_SHOULDER = 6
_LEFT_HIP = 11
_RIGHT_HIP = 12
_LEFT_KNEE = 13
_RIGHT_KNEE = 14
_LEFT_ANKLE = 15
_RIGHT_ANKLE = 16


@dataclass(frozen=True)
class PoseGeometryFeaturesV2:
    """Enhanced geometric features for one person observation at one time point.

    Attributes:
        bbox_width: Bounding box width in pixels.
        bbox_height: Bounding box height in pixels.
        bbox_diagonal: Bounding box diagonal length in pixels.
        aspect_ratio: Height / width ratio (height / max(width, 1e-6)).
        shoulder_midpoint: (x, y) of shoulder midpoint, or fallback.
        hip_midpoint: (x, y) of hip midpoint, or fallback.
        head_point: (x, y) of head/nose, or fallback.
        torso_vector: (dx, dy) vector pointing from hip to shoulder midpoint.
        torso_angle_deg: Torso orientation angle relative to horizontal in [0, 90] degrees.
        body_center: (x, y) coordinates of body center (hip midpoint or bbox center).
        hip_height_ratio: Ratio of hip Y coordinate relative to bounding box [0, 1].
        keypoint_confidence_mean: Mean confidence of present keypoints in [0, 1].
        keypoints_present_count: Count of present keypoints out of 17.
    """

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


def extract_geometry_features_v2(observation: Any) -> PoseGeometryFeaturesV2:
    """Extract enhanced geometric posture features from a TrackObservation.

    Args:
        observation: A TrackObservation instance.

    Returns:
        PoseGeometryFeaturesV2 containing all geometry attributes.
    """
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

    # Head keypoint (nose or eye midpoint)
    head_kpt = kpts[_NOSE]
    if head_kpt.present and head_kpt.x is not None and head_kpt.y is not None:
        head_pt: tuple[float, float] | None = (head_kpt.x, head_kpt.y)
    else:
        head_pt = _midpoint_or_single(kpts[_LEFT_EYE], kpts[_RIGHT_EYE])

    # Multi-tier torso angle calculation
    torso_vec: tuple[float, float] | None = None
    if shoulder_mid is not None and hip_mid is not None:
        torso_vec = (
            shoulder_mid[0] - hip_mid[0],
            shoulder_mid[1] - hip_mid[1],
        )
        dx = abs(torso_vec[0])
        dy = abs(torso_vec[1])
        if dx == 0.0 and dy == 0.0:
            torso_angle = 90.0
        else:
            torso_angle = math.degrees(math.atan2(dy, dx))
    elif head_pt is not None and hip_mid is not None:
        torso_vec = (
            head_pt[0] - hip_mid[0],
            head_pt[1] - hip_mid[1],
        )
        dx = abs(torso_vec[0])
        dy = abs(torso_vec[1])
        torso_angle = 90.0 if (dx == 0.0 and dy == 0.0) else math.degrees(math.atan2(dy, dx))
    else:
        # Fallback angle derived from bbox aspect ratio
        if aspect_ratio >= 1.6:
            torso_angle = 85.0
        elif aspect_ratio <= 0.6:
            torso_angle = 15.0
        else:
            torso_angle = math.degrees(math.atan2(bbox_h, max(bbox_w, 1e-6)))

    # Body center: hip midpoint fallback to bbox center
    if hip_mid is not None:
        body_center = hip_mid
        hip_h_ratio = (hip_mid[1] - y1) / max(bbox_h, 1e-6)
    else:
        body_center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        hip_h_ratio = 0.5

    # Keypoint statistics
    present_kpts = [k for k in kpts if k.present and k.x is not None and k.y is not None]
    present_count = len(present_kpts)
    conf_mean = (
        sum(k.confidence for k in present_kpts) / present_count if present_count > 0 else 0.0
    )

    return PoseGeometryFeaturesV2(
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
    )
