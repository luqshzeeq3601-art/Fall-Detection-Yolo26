# ruff: noqa: E501
"""V4 Pipeline Freezing & Cryptographic Manifest Generator (Phase 11.7 P11.7-014).

Computes SHA-256 cryptographic hashes for all V4 artifacts (classifier weights,
calibrated YAML config, feature datasets, and core engine sources), producing
models/v4_freeze_manifest.json to freeze the system prior to test split evaluation.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_v4_freeze_manifest() -> dict[str, Any]:
    """Inspect and generate cryptographic freeze manifest for V4 pipeline."""
    base_dir = Path(__file__).resolve().parents[2]

    target_artifacts = [
        ("models/temporal_fall_classifier_v4.json", "V4 Trained GRU Classifier Weights"),
        ("config/fall_detection_v4.yaml", "V4 Calibrated Production Configuration"),
        ("datasets/manifests/v4_multi_source_manifest.json", "V4 Master Dataset Manifest"),
        ("datasets/cache/v4_dev_augmented_features.npz", "V4 Augmented Dev Feature Cache"),
        ("src/eldercare/fall_engine/pipeline_v4.py", "V4 End-to-End Fall Engine Pipeline"),
        ("src/eldercare/fall_engine/features/multiscale.py", "V4 Multi-Scale Feature Extractor"),
        (
            "src/eldercare/fall_engine/suppression/adl_suppressor.py",
            "V4 ADL False-Alert Suppressor",
        ),
        (
            "src/eldercare/fall_engine/normalization/camera_normalizer.py",
            "V4 Camera Invariance Normalizer",
        ),
        (
            "src/eldercare/fall_engine/learned_classifier/classifier_v4.py",
            "V4 Recurrent Classifier Architecture",
        ),
    ]

    artifacts_dict = {}
    for rel_path, description in target_artifacts:
        full_path = base_dir / rel_path
        if full_path.is_file():
            sha256_hash = compute_sha256(full_path)
            size_bytes = full_path.stat().st_size
            artifacts_dict[rel_path.replace("\\", "/")] = {
                "sha256": sha256_hash,
                "size_bytes": size_bytes,
                "description": description,
                "status": "FROZEN",
            }
        else:
            artifacts_dict[rel_path.replace("\\", "/")] = {
                "status": "NOT_FOUND",
                "description": description,
            }

    manifest = {
        "manifest_version": "4.0.0",
        "phase": "Phase 11.7 — Real-World Deployment Hardening & Model Performance Upgrade",
        "freeze_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_architecture": "GRUClassifierV4",
        "primary_backbone": "yolo26s-pose.pt",
        "calibrated_operational_triplet": {
            "tau_veto": 0.55,
            "tau_trigger": 0.68,
            "tau_confirm": 0.69,
        },
        "multi_scale_windows": {
            "short_sec": 0.5,
            "medium_sec": 1.0,
            "long_sec": 2.0,
        },
        "status": "FROZEN_FOR_TEST_EVALUATION",
        "artifacts": artifacts_dict,
    }

    out_path = base_dir / "models" / "v4_freeze_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest


if __name__ == "__main__":
    m = generate_v4_freeze_manifest()
    print("V4 Freeze Manifest successfully generated:")
    for path, meta in m["artifacts"].items():
        print(
            f" - {path}: {meta.get('sha256', 'MISSING')[:12]}... ({meta.get('size_bytes', 0)} bytes)"
        )
