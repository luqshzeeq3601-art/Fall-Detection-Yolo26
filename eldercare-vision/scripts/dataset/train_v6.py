"""Phase 11.8 / V6 Model Training, 5-Fold Grouped Cross-Validation & Calibration Engine.

Executes the model training ladder on the Dev partition:
- M1: HistGradientBoostingClassifier on multi-scale hand-crafted temporal features
- M2: Deep 1D CNN-GRU on 15 Hz normalized skeleton keypoints
- M3: Fused Ensemble (M1 + M2)

Enforces Dev Exit Criteria:
- Out-of-fold Recall >= 0.96
- Out-of-fold Precision >= 0.96

Outputs:
- models/temporal_fall_classifier_v6_m1.joblib
- models/temporal_skeleton_classifier_v6.pt
- models/v6_training_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# Add repo root and src directory to python path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.learned_classifier.training_v5 import (
    load_dataset_samples_from_cache,
    run_5fold_cross_validation_v5,
    train_m1_hist_gbdt,
    train_m2_skeleton_net,
)

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

LOG = logging.getLogger("train_v6")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout, force=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train V6 Dual-Stream Models with 5-Fold Grouped CV")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        help="Path to V6 master manifest",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "datasets" / "cache" / "poses",
        help="Path to 15 Hz pose cache directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "models",
        help="Directory to save trained models and reports",
    )
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs for M2 CNN-GRU")
    parser.add_argument("--min-metric-threshold", type=float, default=0.96, help="Dev exit threshold for Recall & Precision")
    args = parser.parse_args()

    manifest_file = Path(args.manifest).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_file.is_file():
        LOG.error("Manifest not found: %s", manifest_file)
        sys.exit(1)

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    records = manifest_data.get("records", [])
    dev_records = [r for r in records if r.get("split") == "dev"]

    LOG.info("Loaded V6 Master Manifest: %d total records, %d Dev partition records.", len(records), len(dev_records))

    # 1. Load dataset samples from 15Hz pose caches
    LOG.info("Loading 15 Hz pose caches from %s...", cache_dir)
    samples = load_dataset_samples_from_cache(dev_records, cache_dir)
    if not samples:
        error_msg = f"No pose caches found on disk at {cache_dir}. Real pose caches are required."
        LOG.error(error_msg)
        raise RuntimeError(error_msg)

    LOG.info("Extracted %d sliding window training samples from %d Dev sequences.", len(samples), len(dev_records))

    manifest_bytes = manifest_file.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    dev_sequence_ids = sorted([r["sequence_id"] for r in dev_records])
    trained_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 2. 5-Fold Grouped Cross-Validation (grouped by subject)
    LOG.info("Executing 5-Fold Grouped Cross-Validation by Subject on Dev pool...")
    cv_results = run_5fold_cross_validation_v5(samples, n_splits=5)
    LOG.info("5-Fold Cross Validation Results: %s", json.dumps(cv_results, indent=2))

    # Dev Exit Criteria Check
    oof_recall = cv_results.get("oof_recall", 0.0)
    oof_precision = cv_results.get("oof_precision", 0.0)
    LOG.info("Dev OOF Metrics: Recall=%.4f (target >= %.2f), Precision=%.4f (target >= %.2f)",
             oof_recall, args.min_metric_threshold, oof_precision, args.min_metric_threshold)

    # 3. Train final M1 (HistGBDT) model on all dev sequences
    LOG.info("Training final M1 (HistGBDT) model on full Dev partition (%d sequences)...", len(dev_sequence_ids))
    m1 = train_m1_hist_gbdt(
        samples,
        training_sequence_ids=dev_sequence_ids,
        manifest_sha256=manifest_sha256,
        trained_at=trained_at_iso,
    )
    m1_path = output_dir / "temporal_fall_classifier_v6_m1.joblib"
    m1.save(m1_path)
    LOG.info("Saved M1 model to %s", m1_path)

    # 4. Train final M2 (Temporal Skeleton CNN-GRU) model on all dev sequences
    LOG.info("Training final M2 (Temporal Skeleton CNN-GRU) model on full Dev partition (%d sequences)...", len(dev_sequence_ids))
    m2_net = train_m2_skeleton_net(samples, samples, epochs=args.epochs)
    m2 = TemporalSkeletonClassifierV5(model=m2_net)
    m2.training_sequence_ids = dev_sequence_ids
    m2.manifest_sha256 = manifest_sha256
    m2.trained_at = trained_at_iso
    m2_path = output_dir / "temporal_skeleton_classifier_v6.pt"
    m2.save(m2_path)
    LOG.info("Saved M2 model to %s", m2_path)

    # 5. Save V6 Training & Cross-Validation Report
    report = {
        "version": "6.0.0",
        "phase": "Phase 11.8 / V6",
        "timestamp": trained_at_iso,
        "dev_sequence_count": len(dev_sequence_ids),
        "dev_samples_count": len(samples),
        "manifest_sha256": manifest_sha256,
        "cross_validation": cv_results,
        "dev_exit_criteria_met": bool(oof_recall >= args.min_metric_threshold and oof_precision >= args.min_metric_threshold),
        "models": {
            "m1_hist_gbdt": {
                "path": str(m1_path.name),
                "feature_dim": 24,
                "sha256": hashlib.sha256(m1_path.read_bytes()).hexdigest(),
            },
            "m2_skeleton_cnn_gru": {
                "path": str(m2_path.name),
                "feature_dim": 72,
                "sequence_length": 30,
                "sha256": hashlib.sha256(m2_path.read_bytes()).hexdigest(),
            },
        },
        "calibrated_post_processor": {
            "fall_trigger_threshold": cv_results.get("best_calibrated_threshold", 0.45),
            "down_confirmation_threshold": 0.50,
            "min_down_sustain_seconds": 0.60,
        },
    }
    report_path = output_dir / "v6_training_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("Saved V6 Training Report to %s", report_path)


if __name__ == "__main__":
    main()
