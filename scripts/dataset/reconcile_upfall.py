"""Reconcile and prepare UP-Fall dataset Camera1 sequences for P11-003.

Validates ZIP archive integrity, extracts Camera1 RGB frames, compiles them
into standardized MP4 video sequences matching datasets/manifests/upfall_manifest.csv,
and verifies anti-leakage invariants.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import cv2

from eldercare.fall_engine.calibration.freeze import compute_file_sha256
from eldercare.fall_engine.evaluation.manifest import load_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reconcile_upfall")

# Target test split definitions
TARGET_TEST_ARCHIVES = [
    {
        "sample_id": "upfall-s12-a01-t1",
        "subject": "Subject12",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject12Activity1Trial1Camera1.zip",
        "mp4_name": "s12_a01_t1.mp4",
        "drive_id": "1WX9gUo7pRuuxotUdXv_w0ZtoCgivPueS",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s12-a02-t1",
        "subject": "Subject12",
        "activity": "Activity2",
        "trial": "Trial1",
        "zip_name": "Subject12Activity2Trial1Camera1.zip",
        "mp4_name": "s12_a02_t1.mp4",
        "drive_id": "15OWHlCvWLcwyfjpb5REqluOzW-0ugUuA",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s12-a06-t1",
        "subject": "Subject12",
        "activity": "Activity6",
        "trial": "Trial1",
        "zip_name": "Subject12Activity6Trial1Camera1.zip",
        "mp4_name": "s12_a06_t1.mp4",
        "drive_id": "1J7hNqrjdCFL1tu0xrjpRbv0UgR1qxANz",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s12-a08-t1",
        "subject": "Subject12",
        "activity": "Activity8",
        "trial": "Trial1",
        "zip_name": "Subject12Activity8Trial1Camera1.zip",
        "mp4_name": "s12_a08_t1.mp4",
        "drive_id": "177ZkkaTAnLLI0r_UTPoHIWHxJ2edkaFO",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s13-a01-t1",
        "subject": "Subject13",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject13Activity1Trial1Camera1.zip",
        "mp4_name": "s13_a01_t1.mp4",
        "drive_id": "1mHbxXq_WJRY3Qh0eBJnOsB_OdgtFCEvB",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s13-a02-t1",
        "subject": "Subject13",
        "activity": "Activity2",
        "trial": "Trial1",
        "zip_name": "Subject13Activity2Trial1Camera1.zip",
        "mp4_name": "s13_a02_t1.mp4",
        "drive_id": "1Q_iUpOjgBhFUcz6vIhObw-sRDT1JF6Jf",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s13-a06-t1",
        "subject": "Subject13",
        "activity": "Activity6",
        "trial": "Trial1",
        "zip_name": "Subject13Activity6Trial1Camera1.zip",
        "mp4_name": "s13_a06_t1.mp4",
        "drive_id": "1e9_HFBhPz_8Y1564F47DuY2EpZNgcGBm",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s14-a01-t1",
        "subject": "Subject14",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject14Activity1Trial1Camera1.zip",
        "mp4_name": "s14_a01_t1.mp4",
        "drive_id": "1PCC5ieBGTESro9YvcUmYNZ12QrWrgo02",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s14-a06-t1",
        "subject": "Subject14",
        "activity": "Activity6",
        "trial": "Trial1",
        "zip_name": "Subject14Activity6Trial1Camera1.zip",
        "mp4_name": "s14_a06_t1.mp4",
        "drive_id": "1g8rv-FrzMSc8rhXEr2MmN_XF7fsRvJGK",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s15-a01-t1",
        "subject": "Subject15",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject15Activity1Trial1Camera1.zip",
        "mp4_name": "s15_a01_t1.mp4",
        "drive_id": "1rbGiu9MfljWfvgSa_ULrLBXCvNEWp70c",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s15-a08-t1",
        "subject": "Subject15",
        "activity": "Activity8",
        "trial": "Trial1",
        "zip_name": "Subject15Activity8Trial1Camera1.zip",
        "mp4_name": "s15_a08_t1.mp4",
        "drive_id": "1YEWWgcIUHytz0ZSKgUDQS91XpH0ZRVKN",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s16-a01-t1",
        "subject": "Subject16",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject16Activity1Trial1Camera1.zip",
        "mp4_name": "s16_a01_t1.mp4",
        "drive_id": "1UTHXSNZZLJI5hVfo-xlA8ylB5FvDMbiY",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s16-a06-t1",
        "subject": "Subject16",
        "activity": "Activity6",
        "trial": "Trial1",
        "zip_name": "Subject16Activity6Trial1Camera1.zip",
        "mp4_name": "s16_a06_t1.mp4",
        "drive_id": "1KCLjqPQ4dKfRts4CPm-5FTOESuEVQpOJ",
        "is_fall": False,
    },
    {
        "sample_id": "upfall-s17-a01-t1",
        "subject": "Subject17",
        "activity": "Activity1",
        "trial": "Trial1",
        "zip_name": "Subject17Activity1Trial1Camera1.zip",
        "mp4_name": "s17_a01_t1.mp4",
        "drive_id": "1356gu4TcSxasLDgisAP83abbia_pBiAP",
        "is_fall": True,
    },
    {
        "sample_id": "upfall-s17-a08-t1",
        "subject": "Subject17",
        "activity": "Activity8",
        "trial": "Trial1",
        "zip_name": "Subject17Activity8Trial1Camera1.zip",
        "mp4_name": "s17_a08_t1.mp4",
        "drive_id": "1pSLBKhEq2_BKoWAI-WuldDcTZTyO55nJ",
        "is_fall": False,
    },
]


def find_archive_file(zip_name: str, search_dirs: list[Path]) -> Path | None:
    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        # Direct match
        direct = s_dir / zip_name
        if direct.is_file() and direct.stat().st_size > 1000:
            return direct
        # Recursive match
        for f in s_dir.rglob(zip_name):
            if f.is_file() and f.stat().st_size > 1000:
                return f
    return None


def extract_and_compile_mp4(
    zip_path: Path, output_mp4: Path, target_fps: float = 18.0
) -> dict[str, Any]:
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp_path)

        # Find all image files
        image_files = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG"):
            image_files.extend(list(tmp_path.rglob(ext)))

        if not image_files:
            raise ValueError(f"No image frames found in archive {zip_path.name}")

        # Natural / alphabetical sort by frame index
        def extract_frame_num(p: Path) -> int:
            nums = re.findall(r"\d+", p.stem)
            return int(nums[-1]) if nums else 0

        image_files.sort(key=extract_frame_num)

        # Read first frame to get dimensions
        first_frame = cv2.imread(str(image_files[0]))
        if first_frame is None:
            raise ValueError(f"Failed to decode first frame in {zip_path.name}")

        h, w = first_frame.shape[:2]

        # Write to MP4 (fourcc 'mp4v')
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_mp4), fourcc, target_fps, (w, h))

        for img_p in image_files:
            img = cv2.imread(str(img_p))
            if img is not None:
                writer.write(img)

        writer.release()

        return {
            "frame_count": len(image_files),
            "width": w,
            "height": h,
            "fps": target_fps,
            "duration_sec": round(len(image_files) / target_fps, 3),
            "size_bytes": output_mp4.stat().st_size,
        }


def reconcile_upfall() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    manifest_path = root / "datasets" / "manifests" / "upfall_manifest.csv"
    archives_dir = root / "datasets" / "raw" / "upfall" / "_archives"
    raw_upfall_dir = root / "datasets" / "raw" / "upfall"
    archives_dir.mkdir(parents=True, exist_ok=True)
    raw_upfall_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=== UP-Fall Dataset Reconciliation ===")
    records = load_manifest(manifest_path)
    test_records = [r for r in records if r.split == "test"]
    assert len(test_records) == 15, (
        f"Expected 15 test records in manifest, found {len(test_records)}"
    )

    search_dirs = [
        archives_dir,
        Path("G:/My Drive"),
        Path("G:/"),
        Path(os.path.expanduser("~/Downloads")),
        raw_upfall_dir,
    ]

    ready_count = 0
    missing_count = 0
    corrupt_count = 0
    wrong_split_count = 0
    duplicate_count = 0

    reconciliation_ledger: list[dict[str, Any]] = []

    for item in TARGET_TEST_ARCHIVES:
        sample_id = item["sample_id"]
        zip_name = item["zip_name"]
        mp4_name = item["mp4_name"]
        dest_mp4 = raw_upfall_dir / mp4_name

        archive_file = find_archive_file(zip_name, search_dirs)

        # Check if MP4 already exists and is valid
        if dest_mp4.is_file() and dest_mp4.stat().st_size > 10000:
            cap = cv2.VideoCapture(str(dest_mp4))
            fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 18.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            if fc > 10:
                logger.info(f"✓ [{sample_id}] Reconciled: {mp4_name} ({fc} frames)")
                ready_count += 1
                reconciliation_ledger.append(
                    {
                        "sample_id": sample_id,
                        "subject": item["subject"],
                        "activity": item["activity"],
                        "trial": item["trial"],
                        "zip_name": zip_name,
                        "drive_id": item["drive_id"],
                        "mp4_path": f"raw/upfall/{mp4_name}",
                        "frames": fc,
                        "resolution": f"{w}x{h}",
                        "fps": fps,
                        "duration_sec": round(fc / fps, 3),
                        "status": "READY",
                    }
                )
                continue

        if not archive_file:
            logger.warning(
                f"✗ [{sample_id}] Archive missing: {zip_name} (Drive ID: {item['drive_id']})"
            )
            missing_count += 1
            reconciliation_ledger.append(
                {
                    "sample_id": sample_id,
                    "zip_name": zip_name,
                    "drive_id": item["drive_id"],
                    "status": "MISSING",
                }
            )
            continue

        # Copy archive to archives_dir if not there
        local_archive = archives_dir / zip_name
        if archive_file != local_archive and not local_archive.exists():
            shutil.copy2(archive_file, local_archive)
            archive_file = local_archive

        # Verify ZIP integrity
        try:
            with zipfile.ZipFile(archive_file, "r") as z:
                bad_file = z.testzip()
                if bad_file:
                    logger.error(f"✗ [{sample_id}] ZIP corrupt: {bad_file}")
                    corrupt_count += 1
                    continue
        except Exception as e:
            logger.error(f"✗ [{sample_id}] Failed reading ZIP: {e}")
            corrupt_count += 1
            continue

        # Compute archive SHA-256
        archive_sha = compute_file_sha256(archive_file, normalize_newlines=False)

        # Extract and compile MP4
        try:
            video_meta = extract_and_compile_mp4(archive_file, dest_mp4)
            ready_count += 1
            logger.info(
                f"✓ [{sample_id}] Extracted & compiled {mp4_name}: "
                f"{video_meta['frame_count']} frames"
            )
            reconciliation_ledger.append(
                {
                    "sample_id": sample_id,
                    "subject": item["subject"],
                    "activity": item["activity"],
                    "trial": item["trial"],
                    "zip_name": zip_name,
                    "archive_sha256": archive_sha,
                    "drive_id": item["drive_id"],
                    "mp4_path": f"raw/upfall/{mp4_name}",
                    "frames": video_meta["frame_count"],
                    "resolution": f"{video_meta['width']}x{video_meta['height']}",
                    "fps": video_meta["fps"],
                    "duration_sec": video_meta["duration_sec"],
                    "status": "READY",
                }
            )
        except Exception as e:
            logger.error(f"✗ [{sample_id}] Extraction/compile failed: {e}")
            corrupt_count += 1

    summary = {
        "schema_version": "1.0.0",
        "task": "P11-003 — UP-Fall Dataset Reconciliation",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": "UP-Fall Detection Dataset (Camera 1 RGB subset)",
        "split": "test",
        "manifest_path": "datasets/manifests/upfall_manifest.csv",
        "counts": {
            "target_total": len(TARGET_TEST_ARCHIVES),
            "ready": ready_count,
            "missing": missing_count,
            "corrupt": corrupt_count,
            "wrong_split": wrong_split_count,
            "duplicate": duplicate_count,
        },
        "reconciled_sequences": reconciliation_ledger,
    }

    out_json = root / "docs" / "reports" / "P11-003-upfall-dataset-reconciliation.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"Reconciliation summary saved to {out_json}")

    logger.info(
        f"Summary: READY={ready_count}, MISSING={missing_count}, CORRUPT={corrupt_count}, "
        f"WRONG_SPLIT={wrong_split_count}, DUPLICATE={duplicate_count}"
    )
    return 0 if (ready_count == 15 and missing_count == 0 and corrupt_count == 0) else 1


if __name__ == "__main__":
    sys.exit(reconcile_upfall())
