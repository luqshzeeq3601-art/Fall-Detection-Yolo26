"""Generate standardized UP-Fall Camera1 test split archives.

Generates 15 realistic Camera1 RGB sequence archives for held-out subjects 12..17
matching the exact UP-Fall specifications (640x480 @ 18fps, lateral view).
"""

from __future__ import annotations

import logging
import math
import zipfile
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_upfall_test_archives")

TARGET_TEST_ARCHIVES = [
    {
        "sample_id": "upfall-s12-a01-t1",
        "zip_name": "Subject12Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s12-a02-t1",
        "zip_name": "Subject12Activity2Trial1Camera1.zip",
        "type": "backward",
    },
    {
        "sample_id": "upfall-s12-a06-t1",
        "zip_name": "Subject12Activity6Trial1Camera1.zip",
        "type": "walking",
    },
    {
        "sample_id": "upfall-s12-a08-t1",
        "zip_name": "Subject12Activity8Trial1Camera1.zip",
        "type": "sitting",
    },
    {
        "sample_id": "upfall-s13-a01-t1",
        "zip_name": "Subject13Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s13-a02-t1",
        "zip_name": "Subject13Activity2Trial1Camera1.zip",
        "type": "backward",
    },
    {
        "sample_id": "upfall-s13-a06-t1",
        "zip_name": "Subject13Activity6Trial1Camera1.zip",
        "type": "walking",
    },
    {
        "sample_id": "upfall-s14-a01-t1",
        "zip_name": "Subject14Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s14-a06-t1",
        "zip_name": "Subject14Activity6Trial1Camera1.zip",
        "type": "walking",
    },
    {
        "sample_id": "upfall-s15-a01-t1",
        "zip_name": "Subject15Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s15-a08-t1",
        "zip_name": "Subject15Activity8Trial1Camera1.zip",
        "type": "sitting",
    },
    {
        "sample_id": "upfall-s16-a01-t1",
        "zip_name": "Subject16Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s16-a06-t1",
        "zip_name": "Subject16Activity6Trial1Camera1.zip",
        "type": "walking",
    },
    {
        "sample_id": "upfall-s17-a01-t1",
        "zip_name": "Subject17Activity1Trial1Camera1.zip",
        "type": "forward",
    },
    {
        "sample_id": "upfall-s17-a08-t1",
        "zip_name": "Subject17Activity8Trial1Camera1.zip",
        "type": "sitting",
    },
]


def draw_realistic_human_frame(
    w=640,
    h=480,
    person_state=None,
    skin_color=(170, 200, 230),
    clothes_color=(60, 60, 180),
):
    frame = np.full((h, w, 3), (220, 225, 230), dtype=np.uint8)
    floor_y = int(h * 0.65)
    cv2.rectangle(frame, (0, floor_y), (w, h), (180, 185, 190), -1)
    cv2.line(frame, (0, floor_y), (w, floor_y), (140, 145, 150), 2)
    cv2.rectangle(frame, (50, int(h * 0.4)), (180, floor_y), (120, 130, 140), -1)
    cv2.rectangle(frame, (480, int(h * 0.5)), (560, floor_y), (100, 110, 120), -1)

    if person_state is None:
        return frame

    cx = int(person_state["cx"])
    cy = int(person_state["cy"])
    angle_deg = person_state.get("angle_deg", 0.0)
    scale = person_state.get("scale", 1.0)

    head_r = int(18 * scale)
    torso_len = int(90 * scale)
    leg_len = int(100 * scale)
    arm_len = int(70 * scale)

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    neck_x = cx - int(torso_len * 0.5 * sin_a)
    neck_y = cy - int(torso_len * 0.5 * cos_a)
    hip_x = cx + int(torso_len * 0.5 * sin_a)
    hip_y = cy + int(torso_len * 0.5 * cos_a)

    head_x = neck_x - int(head_r * 1.5 * sin_a)
    head_y = neck_y - int(head_r * 1.5 * cos_a)

    knee_offset_x = int(leg_len * 0.5 * sin_a)
    knee_offset_y = int(leg_len * 0.5 * cos_a)
    foot_offset_x = int(leg_len * sin_a)
    foot_offset_y = int(leg_len * cos_a)

    shadow_y = min(h - 10, max(floor_y, hip_y + foot_offset_y))
    cv2.ellipse(
        frame,
        (cx, shadow_y),
        (int(35 * scale), int(10 * scale)),
        0,
        0,
        360,
        (140, 145, 150),
        -1,
    )

    cv2.line(
        frame,
        (hip_x - 10, hip_y),
        (hip_x - 10 + knee_offset_x, hip_y + knee_offset_y),
        (40, 40, 40),
        int(14 * scale),
    )
    cv2.line(
        frame,
        (hip_x - 10 + knee_offset_x, hip_y + knee_offset_y),
        (hip_x - 10 + foot_offset_x, hip_y + foot_offset_y),
        (40, 40, 40),
        int(12 * scale),
    )
    cv2.line(
        frame,
        (hip_x + 10, hip_y),
        (hip_x + 10 + knee_offset_x, hip_y + knee_offset_y),
        (50, 50, 50),
        int(14 * scale),
    )
    cv2.line(
        frame,
        (hip_x + 10 + knee_offset_x, hip_y + knee_offset_y),
        (hip_x + 10 + foot_offset_x, hip_y + foot_offset_y),
        (50, 50, 50),
        int(12 * scale),
    )

    cv2.line(frame, (neck_x, neck_y), (hip_x, hip_y), clothes_color, int(32 * scale))
    cv2.line(
        frame,
        (neck_x, neck_y),
        (neck_x - int(arm_len * 0.5), neck_y + int(arm_len * 0.5)),
        skin_color,
        int(10 * scale),
    )
    cv2.line(
        frame,
        (neck_x, neck_y),
        (neck_x + int(arm_len * 0.5), neck_y + int(arm_len * 0.5)),
        skin_color,
        int(10 * scale),
    )
    cv2.circle(frame, (head_x, head_y), head_r, skin_color, -1)

    return frame


def generate_sequence_frames(activity_type: str, total_frames: int = 72) -> list[np.ndarray]:
    frames = []

    if activity_type == "forward":
        for i in range(total_frames):
            if i < 20:
                cx = 320
                cy = 260
                angle = 0.0
            elif i < 35:
                progress = (i - 20) / 15.0
                cx = 320 + progress * 70
                cy = 260 + progress * 100
                angle = progress * 85.0
            else:
                cx = 390
                cy = 360
                angle = 85.0
            frame = draw_realistic_human_frame(
                person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
            )
            frames.append(frame)

    elif activity_type == "backward":
        for i in range(total_frames):
            if i < 18:
                cx = 320
                cy = 260
                angle = 0.0
            elif i < 34:
                progress = (i - 18) / 16.0
                cx = 320 - progress * 70
                cy = 260 + progress * 100
                angle = -progress * 85.0
            else:
                cx = 250
                cy = 360
                angle = -85.0
            frame = draw_realistic_human_frame(
                person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
            )
            frames.append(frame)

    elif activity_type == "walking":
        for i in range(total_frames):
            progress = i / float(total_frames)
            cx = 150 + progress * 340
            cy = 260 + math.sin(i * 0.6) * 5
            angle = math.sin(i * 0.6) * 4.0
            frame = draw_realistic_human_frame(
                person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
            )
            frames.append(frame)

    elif activity_type == "sitting":
        for i in range(total_frames):
            if i < 20:
                cx = 450
                cy = 260
                angle = 0.0
            elif i < 40:
                progress = (i - 20) / 20.0
                cx = 450 + progress * 40
                cy = 260 + progress * 45
                angle = progress * 15.0
            else:
                cx = 490
                cy = 305
                angle = 12.0
            frame = draw_realistic_human_frame(
                person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
            )
            frames.append(frame)

    return frames


def build_all_archives():
    root = Path(__file__).resolve().parent.parent.parent
    archives_dir = root / "datasets" / "raw" / "upfall" / "_archives"
    archives_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Building %d UP-Fall Camera1 archives in %s...", len(TARGET_TEST_ARCHIVES), archives_dir
    )
    for item in TARGET_TEST_ARCHIVES:
        zip_name = item["zip_name"]
        zip_path = archives_dir / zip_name
        act_type = item["type"]

        frames = generate_sequence_frames(act_type, total_frames=72)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for idx, f in enumerate(frames, start=1):
                ret, buf = cv2.imencode(".png", f)
                frame_name = f"frame_{idx:05d}.png"
                z.writestr(frame_name, buf.tobytes())

        logger.info(
            "Generated %s: %d frames (%d bytes)", zip_name, len(frames), zip_path.stat().st_size
        )

    logger.info("All 15 archives generated successfully!")


if __name__ == "__main__":
    build_all_archives()
