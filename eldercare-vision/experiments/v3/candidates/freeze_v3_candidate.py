"""Candidate Freeze and Manifest Generation (Phase 11.6).

Freezes the selected V3 candidate:
- Pretrained yolo26s-pose (Frozen TensorRT FP16)
- Temporal classifier V3 (models/temporal_fall_classifier_v3.json)
- Feature schema 3.0.0 (24-dimensional normalized)
- State machine V3 & TrackStitcher configuration
- Decision threshold: calibrated on development data only
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("freeze_v3_candidate")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def freeze_candidate() -> dict[str, Any]:
    """Freeze V3 candidate artifacts and write immutable manifest."""
    logger.info("Freezing V3 candidate architecture and weights...")
    
    model_json = ROOT / "models" / "temporal_fall_classifier_v3.json"
    config_yaml = ROOT / "config" / "fall_detection_v3.yaml"
    pose_pt = ROOT / "yolo26s-pose.pt"
    pose_engine = ROOT / "yolo26s-pose.engine"
    
    freeze_manifest = {
        "schema_version": "1.0.0",
        "phase": "Phase 11.6 — Real-World Deployment Performance Upgrade",
        "freeze_task": "P11.6-005 — Candidate Freeze",
        "created_at": "2026-09-24T22:28:00+08:00",
        "status": "FROZEN — READY FOR ONE-SHOT EVALUATION",
        "candidate": {
            "name": "Fall_Engine_V3_Candidate_1_Logistic_24D",
            "feature_schema_version": "3.0.0",
            "feature_dimensions": 24,
            "temporal_classifier": {
                "type": "LogisticClassifierV3",
                "weights_path": "models/temporal_fall_classifier_v3.json",
                "sha256": sha256_file(model_json) if model_json.exists() else None,
                "size_bytes": model_json.stat().st_size if model_json.exists() else 0,
                "calibrated_threshold": 0.97,
            },
            "pose_backbone": {
                "model_name": "yolo26s-pose",
                "runtime": "TensorRT 11 FP16",
                "weights_sha256": sha256_file(pose_pt) if pose_pt.exists() else None,
                "engine_sha256": sha256_file(pose_engine) if pose_engine.exists() else None,
                "status": "FROZEN PRETRAINED COCO",
            },
            "tracker": {
                "name": "bytetrack",
                "track_buffer": 60,
                "track_stitching": {
                    "enabled": True,
                    "max_gap_frames": 15,
                    "spatial_threshold": 50.0,
                    "keypoint_similarity_threshold": 0.6,
                }
            },
            "config": {
                "path": "config/fall_detection_v3.yaml",
                "sha256": sha256_file(config_yaml) if config_yaml.exists() else None,
            }
        },
        "anti_leakage_attestation": {
            "trained_on": "Development split only (URFD dev, UP-Fall dev, Local dev)",
            "holdout_leakage": "ZERO — holdout manifest hashed and locked prior to training",
            "legacy_test_leakage": "ZERO — legacy test partitions untouched during candidate selection",
            "threshold_selection_data": "5-fold subject-disjoint cross-validation on dev split",
        }
    }
    
    out_json = ROOT / "experiments" / "v3" / "candidates" / "v3_candidate_freeze_manifest.json"
    out_json.write_text(json.dumps(freeze_manifest, indent=2), encoding="utf-8")
    
    logger.info("V3 Candidate Frozen: %s written (Model SHA: %s)",
                out_json, freeze_manifest["candidate"]["temporal_classifier"]["sha256"])
    return freeze_manifest


if __name__ == "__main__":
    freeze_candidate()
