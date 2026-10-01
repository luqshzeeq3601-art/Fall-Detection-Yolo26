"""Synthetic pose and track fixtures for Temporal Fall Engine testing (P4-001).

Pure, deterministic, CPU-safe test fixtures covering standard activities of
daily living (ADLs) and fall dynamics. All fixtures build directly upon the
Phase 2 (`Keypoint`, `PersonPose`, `PoseFrame`) and Phase 3 (`TrackedPerson`,
`TrackedFrame`, `TrackObservation`, `TrackHistory`) domain models.

Zero framework dependencies (no torch, ultralytics, cv2). Zero sleeps.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from eldercare.vision.pose.adapter import (
    KEYPOINT_COUNT,
    Keypoint,
    PersonPose,
)
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import TrackObservation

# COCO Keypoint Index Constants
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_ELBOW = 7
RIGHT_ELBOW = 8
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
LEFT_KNEE = 13
RIGHT_KNEE = 14
LEFT_ANKLE = 15
RIGHT_ANKLE = 16


def make_keypoints(
    coords_map: dict[int, tuple[float, float] | tuple[float, float, float] | None],
    *,
    default_conf: float = 0.90,
) -> tuple[Keypoint, ...]:
    """Build a valid tuple of 17 Keypoint objects.

    Args:
        coords_map: Mapping from keypoint index (0..16) to:
            - `(x, y)`: present keypoint with `default_conf`
            - `(x, y, conf)`: present keypoint with custom confidence
            - `None`: absent/missing keypoint (`present=False`, coords `None`, conf `0.0`)
        default_conf: Default confidence for `(x, y)` tuples.
    """
    keypoints: list[Keypoint] = []
    for i in range(KEYPOINT_COUNT):
        entry = coords_map.get(i)
        if entry is None:
            keypoints.append(Keypoint(x=None, y=None, confidence=0.0, present=False))
        elif len(entry) == 2:
            x, y = entry
            keypoints.append(
                Keypoint(x=float(x), y=float(y), confidence=float(default_conf), present=True)
            )
        elif len(entry) == 3:
            x, y, conf = entry
            if x is None or y is None:
                keypoints.append(
                    Keypoint(x=None, y=None, confidence=float(conf or 0.0), present=False)
                )
            else:
                keypoints.append(
                    Keypoint(x=float(x), y=float(y), confidence=float(conf), present=True)
                )
        else:
            raise ValueError(f"Invalid keypoint entry at index {i}: {entry!r}")
    return tuple(keypoints)


def make_standing_pose(
    center_x: float = 320.0,
    base_y: float = 440.0,
    height: float = 320.0,
    width: float = 120.0,
    *,
    conf: float = 0.92,
) -> PersonPose:
    """Generate a standard upright standing human pose.

    Geometry:
        - Torso orientation: vertical (~90 deg)
        - Aspect ratio (height/width): ~2.67 (> 1.5)
        - Hip midpoint: ~y = base_y - 0.45*height
        - Shoulder midpoint: ~y = base_y - 0.78*height
    """
    half_w = width / 2.0
    shoulder_y = base_y - 0.78 * height
    hip_y = base_y - 0.45 * height
    knee_y = base_y - 0.22 * height
    ankle_y = base_y - 0.02 * height
    head_y = base_y - 0.92 * height

    coords: dict[int, tuple[float, float, float]] = {
        NOSE: (center_x, head_y, conf),
        LEFT_EYE: (center_x - 8.0, head_y - 5.0, conf),
        RIGHT_EYE: (center_x + 8.0, head_y - 5.0, conf),
        LEFT_EAR: (center_x - 18.0, head_y - 2.0, conf),
        RIGHT_EAR: (center_x + 18.0, head_y - 2.0, conf),
        LEFT_SHOULDER: (center_x - half_w * 0.75, shoulder_y, conf),
        RIGHT_SHOULDER: (center_x + half_w * 0.75, shoulder_y, conf),
        LEFT_ELBOW: (center_x - half_w * 0.85, shoulder_y + 0.18 * height, conf),
        RIGHT_ELBOW: (center_x + half_w * 0.85, shoulder_y + 0.18 * height, conf),
        LEFT_WRIST: (center_x - half_w * 0.80, shoulder_y + 0.35 * height, conf),
        RIGHT_WRIST: (center_x + half_w * 0.80, shoulder_y + 0.35 * height, conf),
        LEFT_HIP: (center_x - half_w * 0.45, hip_y, conf),
        RIGHT_HIP: (center_x + half_w * 0.45, hip_y, conf),
        LEFT_KNEE: (center_x - half_w * 0.40, knee_y, conf),
        RIGHT_KNEE: (center_x + half_w * 0.40, knee_y, conf),
        LEFT_ANKLE: (center_x - half_w * 0.38, ankle_y, conf),
        RIGHT_ANKLE: (center_x + half_w * 0.38, ankle_y, conf),
    }
    kpts = make_keypoints(coords, default_conf=conf)
    bbox = (center_x - half_w, base_y - height, center_x + half_w, base_y)
    return PersonPose(bbox_xyxy=bbox, detection_confidence=conf, keypoints=kpts)


def make_sitting_pose(
    center_x: float = 320.0,
    seat_y: float = 380.0,
    torso_height: float = 160.0,
    width: float = 140.0,
    *,
    conf: float = 0.90,
) -> PersonPose:
    """Generate a seated posture with bent knees and lowered torso.

    Geometry:
        - Torso orientation: near vertical (~80-90 deg)
        - Hips lowered to seat height
        - Aspect ratio (height/width): ~1.3-1.5
    """
    half_w = width / 2.0
    shoulder_y = seat_y - torso_height
    head_y = shoulder_y - 40.0
    knee_y = seat_y + 15.0
    ankle_y = seat_y + 70.0

    coords: dict[int, tuple[float, float, float]] = {
        NOSE: (center_x, head_y, conf),
        LEFT_EYE: (center_x - 8.0, head_y - 4.0, conf),
        RIGHT_EYE: (center_x + 8.0, head_y - 4.0, conf),
        LEFT_EAR: (center_x - 18.0, head_y - 2.0, conf),
        RIGHT_EAR: (center_x + 18.0, head_y - 2.0, conf),
        LEFT_SHOULDER: (center_x - half_w * 0.70, shoulder_y, conf),
        RIGHT_SHOULDER: (center_x + half_w * 0.70, shoulder_y, conf),
        LEFT_ELBOW: (center_x - half_w * 0.75, shoulder_y + 60.0, conf),
        RIGHT_ELBOW: (center_x + half_w * 0.75, shoulder_y + 60.0, conf),
        LEFT_WRIST: (center_x - half_w * 0.50, seat_y - 10.0, conf),
        RIGHT_WRIST: (center_x + half_w * 0.50, seat_y - 10.0, conf),
        LEFT_HIP: (center_x - half_w * 0.50, seat_y, conf),
        RIGHT_HIP: (center_x + half_w * 0.50, seat_y, conf),
        LEFT_KNEE: (center_x - half_w * 0.35 + 30.0, knee_y, conf),
        RIGHT_KNEE: (center_x + half_w * 0.35 + 30.0, knee_y, conf),
        LEFT_ANKLE: (center_x - half_w * 0.35 + 30.0, ankle_y, conf),
        RIGHT_ANKLE: (center_x + half_w * 0.35 + 30.0, ankle_y, conf),
    }
    kpts = make_keypoints(coords, default_conf=conf)
    bbox = (center_x - half_w, head_y - 20.0, center_x + half_w + 35.0, ankle_y + 10.0)
    return PersonPose(bbox_xyxy=bbox, detection_confidence=conf, keypoints=kpts)


def make_bending_pose(
    center_x: float = 320.0,
    base_y: float = 440.0,
    bend_forward_offset: float = 90.0,
    *,
    conf: float = 0.88,
) -> PersonPose:
    """Generate a forward-bending pose (picking up an object).

    Geometry:
        - Torso orientation: tilted forward (~30-45 deg)
        - Hip midpoint: ~y = 330.0
        - Shoulder midpoint: ~y = 350.0 (near hip height, shifted forward)
        - Head lowered towards ground
    """
    hip_y = base_y - 130.0
    shoulder_y = hip_y + 15.0
    head_y = shoulder_y + 35.0
    knee_y = base_y - 65.0
    ankle_y = base_y - 5.0

    coords: dict[int, tuple[float, float, float]] = {
        NOSE: (center_x + bend_forward_offset + 30.0, head_y, conf),
        LEFT_EYE: (center_x + bend_forward_offset + 25.0, head_y - 5.0, conf),
        RIGHT_EYE: (center_x + bend_forward_offset + 35.0, head_y - 5.0, conf),
        LEFT_EAR: (center_x + bend_forward_offset + 15.0, head_y - 10.0, conf),
        RIGHT_EAR: (center_x + bend_forward_offset + 25.0, head_y - 10.0, conf),
        LEFT_SHOULDER: (center_x + bend_forward_offset - 25.0, shoulder_y, conf),
        RIGHT_SHOULDER: (center_x + bend_forward_offset + 25.0, shoulder_y, conf),
        LEFT_ELBOW: (center_x + bend_forward_offset - 10.0, shoulder_y + 40.0, conf),
        RIGHT_ELBOW: (center_x + bend_forward_offset + 30.0, shoulder_y + 40.0, conf),
        LEFT_WRIST: (center_x + bend_forward_offset - 5.0, base_y - 30.0, conf),
        RIGHT_WRIST: (center_x + bend_forward_offset + 35.0, base_y - 30.0, conf),
        LEFT_HIP: (center_x - 30.0, hip_y, conf),
        RIGHT_HIP: (center_x + 30.0, hip_y, conf),
        LEFT_KNEE: (center_x - 20.0, knee_y, conf),
        RIGHT_KNEE: (center_x + 20.0, knee_y, conf),
        LEFT_ANKLE: (center_x - 20.0, ankle_y, conf),
        RIGHT_ANKLE: (center_x + 20.0, ankle_y, conf),
    }
    kpts = make_keypoints(coords, default_conf=conf)
    bbox = (
        center_x - 45.0,
        hip_y - 15.0,
        center_x + bend_forward_offset + 45.0,
        base_y,
    )
    return PersonPose(bbox_xyxy=bbox, detection_confidence=conf, keypoints=kpts)


def make_fallen_pose(
    center_x: float = 320.0,
    floor_y: float = 430.0,
    length: float = 260.0,
    thickness: float = 70.0,
    direction: str = "right",
    *,
    conf: float = 0.88,
) -> PersonPose:
    """Generate a horizontal lying/fallen pose on the ground.

    Geometry:
        - Torso orientation: near horizontal (~0 to 15 deg)
        - Aspect ratio (height/width): ~0.25 to 0.40 (<< 1.0)
        - All keypoints close to floor level
    """
    half_l = length / 2.0
    sign = 1.0 if direction == "right" else -1.0

    # Keypoint positions distributed horizontally along floor
    head_x = center_x + sign * (half_l - 20.0)
    shoulder_x = center_x + sign * (half_l - 70.0)
    hip_x = center_x - sign * 20.0
    knee_x = center_x - sign * 70.0
    ankle_x = center_x - sign * (half_l - 15.0)

    y_mid = floor_y - thickness / 2.0

    coords: dict[int, tuple[float, float, float]] = {
        NOSE: (head_x, y_mid, conf),
        LEFT_EYE: (head_x - 4.0, y_mid - 8.0, conf),
        RIGHT_EYE: (head_x + 4.0, y_mid - 8.0, conf),
        LEFT_EAR: (head_x - 12.0, y_mid - 5.0, conf),
        RIGHT_EAR: (head_x + 12.0, y_mid - 5.0, conf),
        LEFT_SHOULDER: (shoulder_x, y_mid - 18.0, conf),
        RIGHT_SHOULDER: (shoulder_x, y_mid + 18.0, conf),
        LEFT_ELBOW: (shoulder_x - sign * 25.0, y_mid - 25.0, conf),
        RIGHT_ELBOW: (shoulder_x - sign * 25.0, y_mid + 25.0, conf),
        LEFT_WRIST: (shoulder_x - sign * 50.0, y_mid - 20.0, conf),
        RIGHT_WRIST: (shoulder_x - sign * 50.0, y_mid + 20.0, conf),
        LEFT_HIP: (hip_x, y_mid - 15.0, conf),
        RIGHT_HIP: (hip_x, y_mid + 15.0, conf),
        LEFT_KNEE: (knee_x, y_mid - 10.0, conf),
        RIGHT_KNEE: (knee_x, y_mid + 10.0, conf),
        LEFT_ANKLE: (ankle_x, y_mid - 8.0, conf),
        RIGHT_ANKLE: (ankle_x, y_mid + 8.0, conf),
    }
    kpts = make_keypoints(coords, default_conf=conf)
    bbox = (center_x - half_l, floor_y - thickness, center_x + half_l, floor_y)
    return PersonPose(bbox_xyxy=bbox, detection_confidence=conf, keypoints=kpts)


def interpolate_poses(pose_a: PersonPose, pose_b: PersonPose, alpha: float) -> PersonPose:
    """Linearly interpolate between two PersonPose instances (alpha in [0, 1])."""
    clamped_alpha = max(0.0, min(1.0, float(alpha)))
    inv_alpha = 1.0 - clamped_alpha

    # Interpolate bbox
    b_a = pose_a.bbox_xyxy
    b_b = pose_b.bbox_xyxy
    interp_bbox = (
        b_a[0] * inv_alpha + b_b[0] * clamped_alpha,
        b_a[1] * inv_alpha + b_b[1] * clamped_alpha,
        b_a[2] * inv_alpha + b_b[2] * clamped_alpha,
        b_a[3] * inv_alpha + b_b[3] * clamped_alpha,
    )

    # Interpolate confidence
    interp_conf = (
        pose_a.detection_confidence * inv_alpha + pose_b.detection_confidence * clamped_alpha
    )

    # Interpolate keypoints
    interp_kpts: list[Keypoint] = []
    for k_a, k_b in zip(pose_a.keypoints, pose_b.keypoints, strict=True):
        if (
            k_a.present
            and k_b.present
            and k_a.x is not None
            and k_b.x is not None
            and k_a.y is not None
            and k_b.y is not None
        ):
            ix = k_a.x * inv_alpha + k_b.x * clamped_alpha
            iy = k_a.y * inv_alpha + k_b.y * clamped_alpha
            iconf = k_a.confidence * inv_alpha + k_b.confidence * clamped_alpha
            interp_kpts.append(Keypoint(x=ix, y=iy, confidence=iconf, present=True))
        elif k_a.present and k_a.x is not None and k_a.y is not None:
            interp_kpts.append(
                Keypoint(x=k_a.x, y=k_a.y, confidence=k_a.confidence * inv_alpha, present=True)
            )
        elif k_b.present and k_b.x is not None and k_b.y is not None:
            interp_kpts.append(
                Keypoint(x=k_b.x, y=k_b.y, confidence=k_b.confidence * clamped_alpha, present=True)
            )
        else:
            interp_kpts.append(Keypoint(x=None, y=None, confidence=0.0, present=False))

    return PersonPose(
        bbox_xyxy=interp_bbox, detection_confidence=interp_conf, keypoints=tuple(interp_kpts)
    )


def build_track_observation(
    person: PersonPose,
    *,
    camera_id: str = "cam-01",
    track_id: int | None = 1,
    timestamp: float = 0.0,
    image_width: int = 640,
    image_height: int = 480,
) -> TrackObservation:
    """Wrap a PersonPose in a validated TrackObservation."""
    return TrackObservation(
        camera_id=camera_id,
        track_id=track_id,
        timestamp=float(timestamp),
        bbox_xyxy=person.bbox_xyxy,
        detection_confidence=person.detection_confidence,
        keypoints=person.keypoints,
        image_width=image_width,
        image_height=image_height,
    )


# --- Full Scenario Sequence Generators --------------------------------------


def generate_walking_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 2.0,
    fps: float = 15.0,
    start_time: float = 0.0,
    start_x: float = 180.0,
    velocity_x: float = 60.0,  # pixels per sec
) -> tuple[TrackObservation, ...]:
    """Generate a sequence representing normal upright walking across the frame.

    Properties:
        - High aspect ratio (> 1.5)
        - Upright torso orientation (~90 deg)
        - Near-zero vertical velocity
        - Steady horizontal translation
    """
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    for i in range(total_frames):
        t = start_time + i * dt
        curr_x = start_x + velocity_x * (i * dt)
        # Small walking bounce
        bounce_y = 4.0 * math.sin(2.0 * math.pi * 2.0 * (i * dt))
        pose = make_standing_pose(center_x=curr_x, base_y=440.0 + bounce_y)
        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def generate_sitting_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 3.0,
    fps: float = 15.0,
    sit_start_sec: float = 0.8,
    sit_duration_sec: float = 1.2,
    start_time: float = 0.0,
    center_x: float = 320.0,
) -> tuple[TrackObservation, ...]:
    """Generate a sequence of standing -> gradual sitting down -> seated immobility.

    Properties:
        - Smooth vertical descent over 1.0-1.5s (low peak velocity, << fall velocity)
        - Upright torso throughout
        - Aspect ratio stays >= 1.2
    """
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    standing = make_standing_pose(center_x=center_x, base_y=440.0)
    seated = make_sitting_pose(center_x=center_x, seat_y=380.0)

    for i in range(total_frames):
        elapsed = i * dt
        t = start_time + elapsed

        if elapsed < sit_start_sec:
            pose = standing
        elif elapsed < sit_start_sec + sit_duration_sec:
            alpha = (elapsed - sit_start_sec) / sit_duration_sec
            pose = interpolate_poses(standing, seated, alpha)
        else:
            pose = seated

        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def generate_bending_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 2.5,
    fps: float = 15.0,
    bend_start_sec: float = 0.5,
    bend_down_duration: float = 0.5,
    bend_hold_duration: float = 0.5,
    recover_duration: float = 0.5,
    start_time: float = 0.0,
    center_x: float = 320.0,
) -> tuple[TrackObservation, ...]:
    """Generate a sequence of standing -> forward bending -> recovery to upright.

    Properties:
        - Temporary torso orientation drop to ~30-45 deg
        - Rapid return to upright within 1.5s total
        - Does NOT remain low
    """
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    standing = make_standing_pose(center_x=center_x, base_y=440.0)
    bent = make_bending_pose(center_x=center_x, base_y=440.0)

    t1 = bend_start_sec
    t2 = t1 + bend_down_duration
    t3 = t2 + bend_hold_duration
    t4 = t3 + recover_duration

    for i in range(total_frames):
        elapsed = i * dt
        t = start_time + elapsed

        if elapsed < t1:
            pose = standing
        elif elapsed < t2:
            alpha = (elapsed - t1) / bend_down_duration
            pose = interpolate_poses(standing, bent, alpha)
        elif elapsed < t3:
            pose = bent
        elif elapsed < t4:
            alpha = (elapsed - t3) / recover_duration
            pose = interpolate_poses(bent, standing, alpha)
        else:
            pose = standing

        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def generate_slow_liedown_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 4.0,
    fps: float = 15.0,
    transition_start_sec: float = 0.5,
    transition_duration_sec: float = 2.5,
    start_time: float = 0.0,
    center_x: float = 320.0,
) -> tuple[TrackObservation, ...]:
    """Generate a sequence of intentional slow lying down on bed/floor.

    Properties:
        - Long transition duration (2.5s)
        - Very low vertical velocity / acceleration
    """
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    standing = make_standing_pose(center_x=center_x, base_y=440.0)
    fallen = make_fallen_pose(center_x=center_x, floor_y=440.0)

    for i in range(total_frames):
        elapsed = i * dt
        t = start_time + elapsed

        if elapsed < transition_start_sec:
            pose = standing
        elif elapsed < transition_start_sec + transition_duration_sec:
            alpha = (elapsed - transition_start_sec) / transition_duration_sec
            pose = interpolate_poses(standing, fallen, alpha)
        else:
            pose = fallen

        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def generate_fall_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 4.0,
    fps: float = 15.0,
    fall_start_sec: float = 1.0,
    descent_duration_sec: float = 0.35,
    direction: str = "right",
    start_time: float = 0.0,
    center_x: float = 320.0,
) -> tuple[TrackObservation, ...]:
    """Generate a rapid human fall sequence.

    Timeline:
        - Pre-fall (0.0 .. fall_start_sec): standing upright
        - Rapid descent (fall_start .. fall_start + descent_duration): rapid collapse to floor
          (high vertical velocity, rapid torso angle change ~90 -> ~0 deg, aspect ratio collapse)
        - Post-fall down confirmation (fall_start + descent_duration .. end):
          persistent low/horizontal state
    """
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    standing = make_standing_pose(center_x=center_x, base_y=440.0)
    fallen = make_fallen_pose(center_x=center_x + 40.0, floor_y=440.0, direction=direction)

    fall_end_sec = fall_start_sec + descent_duration_sec

    for i in range(total_frames):
        elapsed = i * dt
        t = start_time + elapsed

        if elapsed < fall_start_sec:
            pose = standing
        elif elapsed < fall_end_sec:
            alpha = (elapsed - fall_start_sec) / descent_duration_sec
            # Non-linear acceleration for rapid descent
            accel_alpha = alpha * alpha
            pose = interpolate_poses(standing, fallen, accel_alpha)
        else:
            pose = fallen

        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def generate_fall_with_recovery_sequence(
    *,
    camera_id: str = "cam-01",
    track_id: int = 1,
    duration_sec: float = 6.0,
    fps: float = 15.0,
    fall_start_sec: float = 0.8,
    descent_duration_sec: float = 0.35,
    down_duration_sec: float = 1.8,
    recovery_duration_sec: float = 1.5,
    start_time: float = 0.0,
    center_x: float = 320.0,
) -> tuple[TrackObservation, ...]:
    """Generate a fall sequence followed by recovery back to upright standing."""
    total_frames = int(round(duration_sec * fps))
    dt = 1.0 / fps
    observations: list[TrackObservation] = []

    standing = make_standing_pose(center_x=center_x, base_y=440.0)
    fallen = make_fallen_pose(center_x=center_x + 30.0, floor_y=440.0)

    t_fall_start = fall_start_sec
    t_fall_end = t_fall_start + descent_duration_sec
    t_rec_start = t_fall_end + down_duration_sec
    t_rec_end = t_rec_start + recovery_duration_sec

    for i in range(total_frames):
        elapsed = i * dt
        t = start_time + elapsed

        if elapsed < t_fall_start:
            pose = standing
        elif elapsed < t_fall_end:
            alpha = (elapsed - t_fall_start) / descent_duration_sec
            pose = interpolate_poses(standing, fallen, alpha * alpha)
        elif elapsed < t_rec_start:
            pose = fallen
        elif elapsed < t_rec_end:
            alpha = (elapsed - t_rec_start) / recovery_duration_sec
            pose = interpolate_poses(fallen, standing, alpha)
        else:
            pose = standing

        observations.append(
            build_track_observation(
                pose,
                camera_id=camera_id,
                track_id=track_id,
                timestamp=t,
            )
        )
    return tuple(observations)


def mask_missing_keypoints(
    observation: TrackObservation,
    missing_indices: Sequence[int],
) -> TrackObservation:
    """Create a copy of TrackObservation with specified keypoints marked absent."""
    missing_set = set(missing_indices)
    new_kpts: list[Keypoint] = []
    for idx, kpt in enumerate(observation.keypoints):
        if idx in missing_set:
            new_kpts.append(Keypoint(x=None, y=None, confidence=0.0, present=False))
        else:
            new_kpts.append(kpt)

    return TrackObservation(
        camera_id=observation.camera_id,
        track_id=observation.track_id,
        timestamp=observation.timestamp,
        bbox_xyxy=observation.bbox_xyxy,
        detection_confidence=observation.detection_confidence,
        keypoints=tuple(new_kpts),
        image_width=observation.image_width,
        image_height=observation.image_height,
    )


def populate_history_from_sequence(
    sequence: Sequence[TrackObservation],
    *,
    config: TrackHistoryConfig | None = None,
) -> TrackHistory:
    """Helper to populate a TrackHistory store from a sequence of observations."""
    history = TrackHistory(config=config)
    for obs in sequence:
        history.append(obs)
    return history
