"""Dataset reconciliation script for URFD test set (P11-002)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2

from eldercare.fall_engine.calibration.freeze import compute_file_sha256
from eldercare.fall_engine.evaluation.manifest import load_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reconcile_urfd")


def reconcile_urfd_test_set() -> dict:
    root = Path(__file__).resolve().parent.parent.parent
    manifest_path = root / "datasets" / "manifests" / "urfd_manifest.csv"
    records = load_manifest(manifest_path)

    test_records = [r for r in records if r.split == "test"]
    dev_records = [r for r in records if r.split == "dev"]

    assert len(test_records) == 28, f"Expected 28 test records, got {len(test_records)}"
    assert len(dev_records) == 42, f"Expected 42 dev records, got {len(dev_records)}"

    test_seq_ids = {r.sequence_id for r in test_records}
    dev_seq_ids = {r.sequence_id for r in dev_records}
    assert len(test_seq_ids.intersection(dev_seq_ids)) == 0, "Dev/test sequence overlap detected!"

    reconciliation = {
        "dataset": "URFD",
        "manifest_path": str(manifest_path.relative_to(root)),
        "manifest_normalized_lf_sha256": compute_file_sha256(
            manifest_path, normalize_newlines=True
        ),
        "total_manifest_records": len(records),
        "test_records_count": len(test_records),
        "test_falls_count": sum(1 for r in test_records if r.is_fall),
        "test_adls_count": sum(1 for r in test_records if not r.is_fall),
        "sequences": [],
    }

    for r in test_records:
        vid_path = root / "datasets" / r.path_local
        assert vid_path.is_file(), f"Missing video: {vid_path}"
        cap = cv2.VideoCapture(str(vid_path))
        assert cap.isOpened(), f"Cannot open video: {vid_path}"

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration_sec = frame_count / fps if fps > 0 else 0

        # Verify decode
        ret, _ = cap.read()
        assert ret, f"Failed to decode frame 0 for {vid_path}"
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count // 2))
        ret_mid, _ = cap.read()
        assert ret_mid, f"Failed to decode mid frame for {vid_path}"
        cap.release()

        seq_entry = {
            "sample_id": r.sample_id,
            "sequence_id": r.sequence_id,
            "activity": r.activity,
            "is_fall": r.is_fall,
            "fall_type": r.fall_type,
            "path_local": r.path_local,
            "file_size_bytes": vid_path.stat().st_size,
            "sha256": compute_file_sha256(vid_path, normalize_newlines=False),
            "fps": fps,
            "frame_count": frame_count,
            "resolution": f"{width}x{height}",
            "duration_sec": round(duration_sec, 3),
            "status": "VERIFIED_DECODABLE",
        }
        reconciliation["sequences"].append(seq_entry)
        logger.info(
            "Verified %s: %dx%d @ %.1f fps, %d frames (%.2fs)",
            r.sample_id,
            width,
            height,
            fps,
            frame_count,
            duration_sec,
        )

    out_file = root / "docs" / "reports" / "P11-002-urfd-dataset-reconciliation.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")
    logger.info(f"Reconciliation artifact written to {out_file}")
    return reconciliation


if __name__ == "__main__":
    reconcile_urfd_test_set()
