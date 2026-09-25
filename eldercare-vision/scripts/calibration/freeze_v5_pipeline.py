"""Phase 11.8 V5 Pipeline & Model Artifact Freezing Engine (P11.8-023).

Cryptographically locks all V5 models, configurations, and manifests with SHA-256 hashes
into models/v5_freeze_manifest.json prior to held-out evaluation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("freeze_v5_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def sha256_file(path: Path) -> str:
    """Compute SHA-256 over raw file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_v5_pipeline(repo_root: Path = ROOT) -> Path:
    """Scan and lock all V5 artifacts."""
    artifacts_to_freeze = [
        "models/temporal_skeleton_classifier_v5.pt",
        "models/temporal_fall_classifier_v5_m1.joblib",
        "models/v5_model_ablation_report.json",
        "datasets/manifests/v5_public_manifest.json",
        "config/phase_gate_targets.yaml",
        "src/eldercare/fall_engine/pipeline_v5.py",
        "scripts/dataset/evaluate_v5.py",
    ]

    manifest_entries: dict[str, dict[str, Any]] = {}
    for rel_str in artifacts_to_freeze:
        file_path = repo_root / rel_str
        if not file_path.is_file():
            LOG.warning("Artifact file not found on disk, skipping: %s", rel_str)
            continue

        file_hash = sha256_file(file_path)
        file_size = file_path.stat().st_size
        manifest_entries[rel_str] = {
            "sha256": file_hash,
            "size_bytes": file_size,
            "modified_time": datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        LOG.info("Locked %s -> SHA-256: %s (%d bytes)", rel_str, file_hash, file_size)

    freeze_manifest = {
        "manifest_version": "5.0.0",
        "phase": "11.8",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "total_artifacts": len(manifest_entries),
        "artifacts": manifest_entries,
    }

    out_file = repo_root / "models" / "v5_freeze_manifest.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(freeze_manifest, indent=2), encoding="utf-8")
    LOG.info("Successfully wrote V5 freeze manifest to %s", out_file)
    return out_file


def main() -> None:
    freeze_v5_pipeline()


if __name__ == "__main__":
    main()
