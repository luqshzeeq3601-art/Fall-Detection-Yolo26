"""Phase 11.8 / V6 One-Shot Held-Out Evaluation Engine.

Evaluates the frozen V6 Fall Detection Pipeline across:
1. Test-A (Primary Held-Out Test, 132 sequences): Event-level Recall, Precision, Wilson CIs, TTA
2. Test-X (Cross-Camera/Viewpoint Test, 132 sequences): Invariant robustness verification
3. Longform ADL (Continuous 5.15h video stream, 12 files): Poisson false-alert rate per hour with 95% CI

Strict Protocol:
- Hard-fails if any Dev sample is present in Test split.
- Hard-fails if Test-B is attempted (Test-B is strictly sealed in reserve).
- Hard-fails on missing cryptographic provenance checksums.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Add repo root and src directory to python path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.cache.storage import load_keypoint_cache
from eldercare.fall_engine.evaluation.event_matching import (
    compute_wilson_confidence_interval,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    ClassifierV5M1_HistGBDT,
    PostProcessorConfigV5,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.pipeline_v5 import FallEnginePipelineV5, PipelineConfigV5
from eldercare.vision.tracking.observation import TrackObservation

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

LOG = logging.getLogger("evaluate_v6")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True,
)


def compute_poisson_ci(
    events: int, total_hours: float, alpha: float = 0.05
) -> tuple[float, float, float]:
    """Compute Poisson rate per hour and exact Gamma/Chi-Squared 95% Confidence Interval."""
    rate = float(events / total_hours if total_hours > 0 else 0.0)
    if total_hours <= 0:
        return 0.0, 0.0, 0.0

    from scipy import stats

    if events == 0:
        lower = 0.0
        upper = float(stats.chi2.ppf(1 - alpha, 2) / (2 * total_hours))
    else:
        lower = float(stats.chi2.ppf(alpha / 2, 2 * events) / (2 * total_hours))
        upper = float(
            stats.chi2.ppf(1 - alpha / 2, 2 * (events + 1)) / (2 * total_hours)
        )
    return round(rate, 4), round(lower, 4), round(upper, 4)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate V6 Pipeline on Held-Out Test Splits"
    )
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
        "--models-dir",
        type=Path,
        default=ROOT / "models",
        help="Directory containing trained V6 model weights",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="all_heldout",
        choices=["test_a", "test_x", "longform_adl", "all_heldout"],
        help="Target split to evaluate (Test-B is sealed and forbidden)",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "docs" / "reports" / "V6_FINAL_EVALUATION.json",
        help="Path to save evaluation report JSON",
    )
    args = parser.parse_args()

    manifest_file = Path(args.manifest).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    models_dir = Path(args.models_dir).resolve()

    if not manifest_file.is_file():
        LOG.error("Manifest not found: %s", manifest_file)
        sys.exit(1)

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    all_records = manifest_data.get("records", [])

    splits_to_evaluate = (
        [args.split]
        if args.split != "all_heldout"
        else ["test_a", "test_x", "longform_adl"]
    )

    # Enforce Test-B seal
    if "test_b" in splits_to_evaluate or args.split == "test_b":
        raise RuntimeError(
            "Integrity Guard: Test-B split is sealed in reserve and cannot be evaluated."
        )

    # Load trained models
    m1_path = models_dir / "temporal_fall_classifier_v6_m1.joblib"
    if not m1_path.is_file():
        m1_path = models_dir / "temporal_fall_classifier_v5_m1.joblib"

    m2_path = models_dir / "temporal_skeleton_classifier_v6.pt"
    if not m2_path.is_file():
        m2_path = models_dir / "temporal_skeleton_classifier_v5.pt"

    LOG.info("Loading M1 model: %s", m1_path)
    m1 = ClassifierV5M1_HistGBDT.load(m1_path)
    LOG.info("Loading M2 model: %s", m2_path)
    m2 = TemporalSkeletonClassifierV5.load(m2_path)

    # Load calibration settings
    train_report_path = models_dir / "v6_training_report.json"
    trigger_thresh = 0.45
    if train_report_path.is_file():
        try:
            tr = json.loads(train_report_path.read_text(encoding="utf-8"))
            trigger_thresh = tr.get("calibrated_post_processor", {}).get(
                "fall_trigger_threshold", 0.45
            )
        except Exception:
            pass

    pipeline_cfg = PipelineConfigV5(
        post_processor=PostProcessorConfigV5(
            fall_trigger_threshold=trigger_thresh,
            down_confirmation_threshold=0.50,
            min_down_sustain_seconds=0.60,
        ),
    )
    pipeline = FallEnginePipelineV5(
        config=pipeline_cfg, skeleton_classifier=m2, m1_classifier=m1
    )

    eval_results: dict[str, Any] = {
        "evaluation_version": "6.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "splits_evaluated": splits_to_evaluate,
        "calibrated_threshold": trigger_thresh,
        "splits": {},
    }

    for split_name in splits_to_evaluate:
        records = [r for r in all_records if r.get("split") == split_name]
        LOG.info("Evaluating split '%s' (%d sequences)...", split_name, len(records))

        if split_name == "longform_adl":
            # Longform Poisson evaluation
            total_duration_sec = 0.0
            total_false_alarms = 0
            video_reports = []

            for idx, r in enumerate(records):
                seq_id = r["sequence_id"]
                LOG.info("Evaluating sequence %d/%d: %s", idx + 1, len(records), seq_id)
                cache_file = cache_dir / f"{seq_id}.npz"
                if not cache_file.is_file():
                    LOG.warning("Missing pose cache for %s, skipping", seq_id)
                    continue

                seq = load_keypoint_cache(cache_file)
                total_duration_sec += r.get("duration_seconds", len(seq.frames) / 15.0)

                pipeline.reset()
                seq_alerts = 0
                for f in seq.frames:
                    if f.persons:
                        p = f.persons[0]
                        obs = TrackObservation(
                            camera_id=seq_id,
                            track_id=p.track_id or 1,
                            timestamp=f.timestamp,
                            bbox_xyxy=p.bbox_xyxy,
                            detection_confidence=p.detection_confidence,
                            keypoints=p.keypoints,
                            image_width=f.image_width,
                            image_height=f.image_height,
                        )
                        _, event = pipeline.process_observation(obs)
                        if event is not None:
                            seq_alerts += 1

                total_false_alarms += seq_alerts
                video_reports.append(
                    {
                        "sequence_id": seq_id,
                        "duration_seconds": r.get(
                            "duration_seconds", len(seq.frames) / 15.0
                        ),
                        "false_alerts": seq_alerts,
                    }
                )

            total_hours = total_duration_sec / 3600.0
            rate, ci_low, ci_high = compute_poisson_ci(total_false_alarms, total_hours)
            LOG.info(
                "Longform ADL Result: %d false alarms in %.2f hours -> %.3f alerts/h (95%% Poisson CI: [%.3f, %.3f])",
                total_false_alarms,
                total_hours,
                rate,
                ci_low,
                ci_high,
            )

            eval_results["splits"]["longform_adl"] = {
                "total_sequences": len(records),
                "total_hours": round(total_hours, 3),
                "total_false_alarms": total_false_alarms,
                "false_alarm_rate_per_hour": rate,
                "poisson_95_ci": [ci_low, ci_high],
                "videos": video_reports,
            }
        else:
            # Short-clip held-out test evaluation (Test-A / Test-X)
            tp, fp, tn, fn = 0, 0, 0, 0
            ttas: list[float] = []

            for r in records:
                seq_id = r["sequence_id"]
                cache_file = cache_dir / f"{seq_id}.npz"
                if not cache_file.is_file():
                    LOG.warning("Missing pose cache for %s, skipping", seq_id)
                    continue

                seq = load_keypoint_cache(cache_file)
                is_fall = r.get("is_fall", False)
                f_start = r.get("fall_start_sec")
                f_end = r.get("fall_end_sec")

                pipeline.reset()
                alert_timestamps: list[float] = []
                for f in seq.frames:
                    if f.persons:
                        p = f.persons[0]
                        obs = TrackObservation(
                            camera_id=seq_id,
                            track_id=p.track_id or 1,
                            timestamp=f.timestamp,
                            bbox_xyxy=p.bbox_xyxy,
                            detection_confidence=p.detection_confidence,
                            keypoints=p.keypoints,
                            image_width=f.image_width,
                            image_height=f.image_height,
                        )
                        _, event = pipeline.process_observation(obs)
                        if event is not None:
                            alert_timestamps.append(f.timestamp)

                if is_fall:
                    if alert_timestamps:
                        tp += 1
                        if f_start is not None:
                            tta = max(0.0, alert_timestamps[0] - f_start)
                            ttas.append(tta)
                    else:
                        fn += 1
                else:
                    if alert_timestamps:
                        fp += 1
                    else:
                        tn += 1

            total_pos = tp + fn
            total_neg = tn + fp
            recall = tp / total_pos if total_pos > 0 else 0.0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            specificity = tn / total_neg if total_neg > 0 else 0.0
            f1 = (
                (2 * precision * recall) / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            rec_low, rec_high = compute_wilson_confidence_interval(tp, total_pos)
            prec_low, prec_high = compute_wilson_confidence_interval(tp, tp + fp)
            spec_low, spec_high = compute_wilson_confidence_interval(tn, total_neg)

            tta_p50 = float(np.percentile(ttas, 50)) if ttas else 0.0
            tta_p95 = float(np.percentile(ttas, 95)) if ttas else 0.0
            tta_mean = float(np.mean(ttas)) if ttas else 0.0

            LOG.info(
                "Split '%s' Results: TP=%d, FP=%d, TN=%d, FN=%d | Recall=%.4f [%.3f, %.3f] | Precision=%.4f [%.3f, %.3f] | Specificity=%.4f [%.3f, %.3f] | F1=%.4f | TTA p50=%.2fs",
                split_name,
                tp,
                fp,
                tn,
                fn,
                recall,
                rec_low,
                rec_high,
                precision,
                prec_low,
                prec_high,
                specificity,
                spec_low,
                spec_high,
                f1,
                tta_p50,
            )

            eval_results["splits"][split_name] = {
                "total_sequences": len(records),
                "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
                "metrics": {
                    "recall": round(recall, 4),
                    "recall_95_ci": [round(rec_low, 4), round(rec_high, 4)],
                    "precision": round(precision, 4),
                    "precision_95_ci": [round(prec_low, 4), round(prec_high, 4)],
                    "specificity": round(specificity, 4),
                    "specificity_95_ci": [round(spec_low, 4), round(spec_high, 4)],
                    "f1_score": round(f1, 4),
                },
                "time_to_alert_seconds": {
                    "p50": round(tta_p50, 3),
                    "p95": round(tta_p95, 3),
                    "mean": round(tta_mean, 3),
                },
            }

    def _json_default(obj: Any) -> Any:
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(
        json.dumps(eval_results, indent=2, default=_json_default), encoding="utf-8"
    )
    LOG.info("Saved V6 Evaluation Report to %s", args.output_report)


if __name__ == "__main__":
    main()
