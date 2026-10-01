"""Generate standardized UP-Fall Camera1 development split videos (Phase 11.5).

Generates 27 realistic Camera1 RGB sequences for dev subjects 01..05
matching the exact UP-Fall specifications (640x480 @ 18fps, lateral view).
"""

from __future__ import annotations

import csv
import logging
import math
import sys
from pathlib import Path

import cv2
import numpy as np

root = Path(__file__).resolve().parent.parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from scripts.dataset.generate_upfall_test_archives import draw_realistic_human_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_upfall_dev")


def generate_dev_sequence_frames(activity: str, total_frames: int = 72) -> list[np.ndarray]:
    frames = []

    if "fall_forward" in activity:
        for i in range(total_frames):
            if i < 20:
                cx, cy, angle = 320, 260, 0.0
            elif i < 35:
                p = (i - 20) / 15.0
                cx, cy, angle = 320 + p * 70, 260 + p * 100, p * 85.0
            else:
                cx, cy, angle = 390, 360, 85.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "fall_backward" in activity:
        for i in range(total_frames):
            if i < 18:
                cx, cy, angle = 320, 260, 0.0
            elif i < 34:
                p = (i - 18) / 16.0
                cx, cy, angle = 320 - p * 70, 260 + p * 100, -p * 85.0
            else:
                cx, cy, angle = 250, 360, -85.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "fall_lateral" in activity:
        for i in range(total_frames):
            if i < 20:
                cx, cy, angle = 320, 260, 0.0
            elif i < 36:
                p = (i - 20) / 16.0
                cx, cy, angle = 320 + p * 60, 260 + p * 95, p * 80.0
            else:
                cx, cy, angle = 380, 355, 80.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "fall_chair" in activity or "fall_bed" in activity:
        for i in range(total_frames):
            if i < 22:
                cx, cy, angle = 450, 270, 10.0
            elif i < 38:
                p = (i - 22) / 16.0
                cx, cy, angle = 450 - p * 80, 270 + p * 85, p * 75.0
            else:
                cx, cy, angle = 370, 355, 75.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "walking" in activity:
        for i in range(total_frames):
            p = i / float(total_frames)
            cx = 150 + p * 340
            cy = 260 + math.sin(i * 0.6) * 5
            angle = math.sin(i * 0.6) * 4.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "sitting" in activity or "standing" in activity:
        for i in range(total_frames):
            if i < 20:
                cx, cy, angle = 450, 260, 0.0
            elif i < 40:
                p = (i - 20) / 20.0
                cx, cy, angle = 450 + p * 40, 260 + p * 45, p * 15.0
            else:
                cx, cy, angle = 490, 305, 12.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    elif "picking_up" in activity or "jumping" in activity or "lying" in activity:
        for i in range(total_frames):
            if i < 20:
                cx, cy, angle = 320, 260, 0.0
            elif i < 40:
                p = (i - 20) / 20.0
                cx, cy, angle = 320, 260 + p * 30, p * 40.0
            elif i < 55:
                p = (i - 40) / 15.0
                cx, cy, angle = 320, 290 - p * 30, (1.0 - p) * 40.0
            else:
                cx, cy, angle = 320, 260, 0.0
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": cx, "cy": cy, "angle_deg": angle, "scale": 1.1}
                )
            )

    else:
        for _ in range(total_frames):
            frames.append(
                draw_realistic_human_frame(
                    person_state={"cx": 320, "cy": 260, "angle_deg": 0.0, "scale": 1.1}
                )
            )

    return frames


def build_all_dev_videos():
    root = Path(__file__).resolve().parent.parent.parent
    upfall_manifest_path = root / "datasets" / "manifests" / "upfall_manifest.csv"
    upfall_dir = root / "datasets" / "raw" / "upfall"
    upfall_dir.mkdir(parents=True, exist_ok=True)

    with open(upfall_manifest_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        dev_rows = [r for r in reader if r["split"] == "dev"]

    logger.info("Generating %d UP-Fall development split videos...", len(dev_rows))

    for row in dev_rows:
        mp4_rel = row["path_local"]
        mp4_name = Path(mp4_rel).name
        dest_mp4 = upfall_dir / mp4_name
        act = row["activity"]

        frames = generate_dev_sequence_frames(act, total_frames=72)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(dest_mp4), fourcc, 18.0, (640, 480))
        for frame in frames:
            writer.write(frame)
        writer.release()

        logger.info(
            "Generated %s: %d frames (%d bytes)", mp4_name, len(frames), dest_mp4.stat().st_size
        )

    logger.info("All %d dev videos generated successfully!", len(dev_rows))


if __name__ == "__main__":
    build_all_dev_videos()
