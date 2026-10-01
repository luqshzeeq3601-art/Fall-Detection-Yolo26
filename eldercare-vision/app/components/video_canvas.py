"""Video Canvas Annotation for YOLO26 Keypoints, Tracking, and Privacy Redaction."""

from __future__ import annotations

import cv2
import numpy as np

# Standard COCO 17 Keypoint Skeleton Connections
COCO_SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),  # Facial
    (5, 6),                          # Shoulders
    (5, 7), (7, 9),                  # Left arm
    (6, 8), (8, 10),                 # Right arm
    (5, 11), (6, 12),                # Torso
    (11, 12),                        # Hips
    (11, 13), (13, 15),              # Left leg
    (12, 14), (14, 16),              # Right leg
]

COLOR_UPRIGHT = (16, 185, 129)      # Emerald (#10B981 in RGB)
COLOR_KINETIC = (245, 158, 11)      # Amber (#F59E0B)
COLOR_FALL = (239, 68, 68)          # Crimson (#EF4444)
COLOR_JOINT = (37, 99, 235)         # Blue (#2563EB)


def annotate_frame(
    frame: np.ndarray,
    keypoints: np.ndarray | None = None,
    bbox: tuple[int, int, int, int] | None = None,
    track_id: int = 1,
    state: str = "NORMAL",
    privacy_blur: bool = False,
    show_skeleton: bool = True,
    show_bbox: bool = True,
) -> np.ndarray:
    """Draw bounding box, skeleton, velocity vectors, and status overlay on frame."""
    out = frame.copy()
    h, w = out.shape[:2]

    # Select color by state
    if state in ("FALL", "FALL_DETECTED", "CRITICAL"):
        accent_color = COLOR_FALL
        status_label = "CRITICAL: FALL DETECTED"
    elif state in ("FALLING", "KINETIC_DISPLACEMENT"):
        accent_color = COLOR_KINETIC
        status_label = "WARNING: KINETIC DISPLACEMENT"
    else:
        accent_color = COLOR_UPRIGHT
        status_label = "NORMAL: UPRIGHT"

    # Privacy redaction (blur face or upper torso)
    if privacy_blur and bbox is not None:
        bx1, by1, bx2, by2 = bbox
        bx1, by1 = max(0, bx1), max(0, by1)
        bx2, by2 = min(w, bx2), min(h, by2)
        # Blur top 35% of bounding box (head/face area)
        face_h = int((by2 - by1) * 0.35)
        if face_h > 10 and (bx2 - bx1) > 10:
            face_roi = out[by1 : by1 + face_h, bx1:bx2]
            blurred = cv2.GaussianBlur(face_roi, (41, 41), 30)
            out[by1 : by1 + face_h, bx1:bx2] = blurred

    # Draw Bounding Box
    if show_bbox and bbox is not None:
        bx1, by1, bx2, by2 = bbox
        cv2.rectangle(out, (bx1, by1), (bx2, by2), accent_color, 2)
        # Label badge
        label = f"ID #{track_id} | {status_label}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (bx1, max(0, by1 - 22)), (bx1 + tw + 10, max(22, by1)), accent_color, -1)
        cv2.putText(
            out,
            label,
            (bx1 + 5, max(16, by1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # Draw Skeleton Keypoints & Limbs
    if show_skeleton and keypoints is not None and len(keypoints) >= 17:
        # Draw limbs
        for p1, p2 in COCO_SKELETON:
            if p1 < len(keypoints) and p2 < len(keypoints):
                pt1 = keypoints[p1]
                pt2 = keypoints[p2]
                conf1 = pt1[2] if len(pt1) > 2 else 1.0
                conf2 = pt2[2] if len(pt2) > 2 else 1.0
                if conf1 > 0.25 and conf2 > 0.25:
                    x1, y1 = int(pt1[0]), int(pt1[1])
                    x2, y2 = int(pt2[0]), int(pt2[1])
                    cv2.line(out, (x1, y1), (x2, y2), accent_color, 2, cv2.LINE_AA)

        # Draw joints
        for _idx, pt in enumerate(keypoints):
            conf = pt[2] if len(pt) > 2 else 1.0
            if conf > 0.25:
                x, y = int(pt[0]), int(pt[1])
                cv2.circle(out, (x, y), 4, COLOR_JOINT, -1, cv2.LINE_AA)
                cv2.circle(out, (x, y), 2, (255, 255, 255), -1, cv2.LINE_AA)

    # HUD Status Watermark (Top Left)
    cv2.rectangle(out, (10, 10), (220, 42), (255, 255, 255), -1)
    cv2.rectangle(out, (10, 10), (220, 42), (203, 213, 225), 1)
    cv2.putText(
        out,
        f"STATUS: {status_label}",
        (16, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        accent_color,
        1,
        cv2.LINE_AA,
    )

    return out
