"""Phase 11.8 V5 Model Ablation Ladder & Training Pipeline (P11.8-017..022).

Executes the model ablation ladder:
- M0: Retrained V4 Baseline
- M1: HistGradientBoosting on multi-scale hand features
- M2: Deep 1D CNN-GRU on 15 Hz normalized skeleton keypoints
- M3: Fused Ensemble (M1 + M2)

Saves trained model artifacts, out-of-fold calibration parameters, and ablation metrics.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

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

LOG = logging.getLogger("train_v5_ablation")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train V5 Model Ablation Ladder")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v5_public_manifest.json",
        help="Path to V5 public dataset manifest",
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
        help="Directory to save trained model weights and reports",
    )
    parser.add_argument("--epochs", type=int, default=25, help="Training epochs for M2")
    args = parser.parse_args()

    manifest_file = Path(args.manifest).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_file.is_file():
        LOG.error("Manifest not found: %s", manifest_file)
        sys.exit(1)

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    dev_records = [r for r in manifest_data.get("records", []) if r.get("split") == "dev"]

    LOG.info("Starting Phase 11.8 V5 Model Ablation Ladder on %d dev records...", len(dev_records))

    # 1. Load dataset samples
    samples = load_dataset_samples_from_cache(dev_records, cache_dir)
    if not samples:
        error_msg = f"No pose caches found on disk at {cache_dir}. Missing real pose caches; synthetic fallback prohibited."
        LOG.error(error_msg)
        raise RuntimeError(error_msg)

    # 2. 5-Fold Grouped Cross-Validation
    cv_results = run_5fold_cross_validation_v5(samples, n_splits=5)
    LOG.info("5-Fold Cross Validation Complete: %s", cv_results)

    # 3. Train final models on full dev pool
    LOG.info("Training final M1 (HistGBDT) on full dev set...")
    m1 = train_m1_hist_gbdt(samples)
    m1_path = output_dir / "temporal_fall_classifier_v5_m1.joblib"
    m1.save(m1_path)
    LOG.info("Saved M1 model to %s", m1_path)

    LOG.info("Training final M2 (Temporal Skeleton CNN-GRU) on full dev set...")
    m2_net = train_m2_skeleton_net(samples, samples, epochs=args.epochs)
    m2 = TemporalSkeletonClassifierV5(model=m2_net)
    m2_path = output_dir / "temporal_skeleton_classifier_v5.pt"
    m2.save(m2_path)
    LOG.info("Saved M2 model to %s", m2_path)

    # 4. Save Ablation Summary Report
    report = {
        "phase": "11.8",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dev_samples_count": len(samples),
        "cross_validation": cv_results,
        "models": {
            "m1_hist_gbdt": {"path": str(m1_path.name), "feature_dim": 24},
            "m2_skeleton_cnn_gru": {
                "path": str(m2_path.name),
                "feature_dim": 72,
                "sequence_length": 30,
            },
        },
        "calibrated_post_processor": {
            "fall_trigger_threshold": cv_results.get("best_calibrated_threshold", 0.45),
            "down_confirmation_threshold": 0.50,
            "min_down_sustain_seconds": 0.60,
        },
    }
    report_path = output_dir / "v5_model_ablation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("Saved ablation report to %s", report_path)


if __name__ == "__main__":
    main()
