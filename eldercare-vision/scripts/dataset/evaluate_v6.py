"""Phase 11.8 / V6 & V6.1 Event-Level Evaluation Engine.

Evaluates Fall Detection Pipeline configurations with strict EventMatcher logic:
1. EventMatcher temporal window matching: [fall_start - 1.0s, lying_start + 3.0s].
2. Exact unclamped time-to-alert (TTA = alert_timestamp - fall_start).
3. Activity-level breakdown across all UP-Fall & ADL categories.
4. Per-alert sidecar JSON dump with kinetic & geometric diagnostics.
5. In-code deployment gate evaluation with Wilson and Poisson 95% confidence intervals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import replace
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
    AlertEvent,
    EventMatcher,
    EventMatchResult,
    SequenceGroundTruth,
    aggregate_event_results,
    summarize_by_group,
)
from eldercare.fall_engine.evaluation.split_guard import (
    BURNED_SPLITS,
    SEALED_SPLITS,
    DatasetSplitGuard,
    split_role,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.pipeline_v6_1 import (
    FallEnginePipelineV61,
    PipelineConfigV61,
    is_floor_posture,
    observations_from_cached_sequence,
)

LONGFORM_SPLITS = frozenset({"longform_adl", "dev_longform", "longform_adl_heldout"})

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


def evaluate_pipeline_on_manifest(
    manifest_path: Path,
    cache_dir: Path,
    models_dir: Path,
    splits_to_evaluate: list[str],
    output_report_path: Path,
    allow_sealed: bool = False,
    no_fixes: bool = False,
) -> dict[str, Any]:
    """Run fast event-level evaluation on specified splits."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    all_records: list[dict[str, Any]] = manifest_data.get("records", [])

    # Sealed final splits (Test-B, longform_adl_heldout) stay closed until the freeze.
    DatasetSplitGuard.enforce_sealed_access(splits_to_evaluate, allow_sealed)

    # Load trained M2 model (M1 is not part of the V6.1 decision path)
    m2_path = models_dir / "temporal_skeleton_classifier_v6.pt"
    LOG.info("Loading M2 model: %s", m2_path)
    m2 = TemporalSkeletonClassifierV5.load(m2_path)

    # Load the calibrated operating point
    train_report_path = models_dir / "v6_training_report.json"
    tr = json.loads(train_report_path.read_text(encoding="utf-8"))
    cal = tr["calibrated_post_processor"]
    base_cfg = PipelineConfigV61()
    # --no-fixes reproduces V6.1 before the root-cause fixes A/B/C, at the same thresholds.
    fix_a = (
        False
        if no_fixes
        else bool(cal.get("suppress_only_without_kinetic_peak", False))
    )
    edge_bottom = True if no_fixes else bool(cal.get("edge_check_bottom", True))
    identity_jump_frac = None if no_fixes else cal.get("identity_jump_frac")
    stitch_tracks = bool(tr.get("stitch_tracks", False))
    identity_stats: dict[str, dict[str, int]] = {}
    pipeline_cfg = replace(
        base_cfg,
        suppress_only_without_kinetic_peak=fix_a,
        edge_check_bottom=edge_bottom,
        post_processor=replace(
            base_cfg.post_processor,
            fall_trigger_threshold=cal["fall_trigger_threshold"],
            down_confirmation_threshold=cal["down_confirmation_threshold"],
            min_down_sustain_seconds=cal["min_down_sustain_seconds"],
            require_falling_motion=cal.get("require_falling_motion", True),
            suppress_until_upright=cal.get("suppress_until_upright", True),
        ),
    )
    pipeline = FallEnginePipelineV61(skeleton_classifier=m2, config=pipeline_cfg)
    pp = pipeline_cfg.post_processor

    matcher = EventMatcher(early_tolerance_sec=1.0, late_tolerance_sec=3.0)
    all_alert_events_dump: list[dict[str, Any]] = []

    eval_results: dict[str, Any] = {
        "evaluation_version": "6.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline": "FallEnginePipelineV61",
        "model_sha256": hashlib.sha256(m2_path.read_bytes()).hexdigest(),
        "splits_evaluated": splits_to_evaluate,
        "split_roles": {s: split_role(s) for s in splits_to_evaluate},
        "calibrated_parameters": {
            "fall_trigger_threshold": pp.fall_trigger_threshold,
            "down_confirmation_threshold": pp.down_confirmation_threshold,
            "min_down_sustain_seconds": pp.min_down_sustain_seconds,
            "require_falling_motion": pp.require_falling_motion,
            "suppress_until_upright": pp.suppress_until_upright,
            "min_leg_keypoint_confidence": pipeline_cfg.min_leg_keypoint_confidence,
            "edge_margin_px": pipeline_cfg.edge_margin_px,
            "bypass_suppressor_on_floor": pipeline_cfg.bypass_suppressor_on_floor,
            "suppress_only_without_kinetic_peak": fix_a,
            "edge_check_bottom": edge_bottom,
            "identity_jump_frac": identity_jump_frac,
            "stitch_tracks": stitch_tracks,
            "cache_dir": str(cache_dir),
            "no_fixes_mode": no_fixes,
        },
        "identity_jump_filter_frames": identity_stats,
        "splits": {},
        "gate_status": {},
    }

    def run_sequence(
        seq_id: str, cache_file: Path, split_name: str
    ) -> tuple[list[AlertEvent], float]:
        """Run the V6.1 pipeline over one cached sequence; return alerts and duration."""
        seq = load_keypoint_cache(cache_file)
        pipeline.reset()
        alerts: list[AlertEvent] = []
        observations = observations_from_cached_sequence(
            seq,
            seq_id,
            max_center_jump_frac=identity_jump_frac,
            stats=identity_stats.setdefault(split_name, {}),
            stitch_tracks=stitch_tracks,
        )
        for obs in observations:
            sig = pipeline.compute_signals(obs, keep_features=False)
            _, event = pipeline.decision.step(sig)
            if event is not None:
                alerts.append(
                    AlertEvent(
                        timestamp_sec=sig.timestamp,
                        frame_idx=-1,
                        track_id=sig.track_id,
                        confidence=float(sig.p_falling + sig.p_fallen),
                        details={
                            "p_falling": round(sig.p_falling, 4),
                            "p_fallen": round(sig.p_fallen, 4),
                            "is_floor_posture": is_floor_posture(sig, pipeline_cfg),
                        },
                    )
                )
        duration = (
            seq.frames[-1].timestamp - seq.frames[0].timestamp
            if len(seq.frames) > 1
            else 0.0
        )
        return alerts, duration

    def dump_alerts(
        split_name: str, r: dict[str, Any], alerts: list[AlertEvent], is_fall: bool
    ) -> None:
        for a in alerts:
            all_alert_events_dump.append(
                {
                    "sequence_id": r["sequence_id"],
                    "split": split_name,
                    "activity_label": r.get("activity_label", "continuous_activity"),
                    "is_fall_gt": is_fall,
                    "timestamp_sec": round(a.timestamp_sec, 4),
                    "track_id": a.track_id,
                    "confidence": round(a.confidence, 4),
                    **a.details,
                }
            )

    for split_name in splits_to_evaluate:
        records = [r for r in all_records if r.get("split") == split_name]
        LOG.info("Evaluating split '%s' (%d sequences)...", split_name, len(records))

        is_longform = split_name in LONGFORM_SPLITS or any(
            r.get("is_long_form", False) for r in records
        )

        if is_longform:
            total_duration_sec = 0.0
            total_false_alarms = 0
            video_reports: list[dict[str, Any]] = []

            for r in records:
                seq_id = r["sequence_id"]
                cache_file = cache_dir / f"{seq_id}.npz"
                if not cache_file.is_file():
                    LOG.warning("Missing pose cache for %s, skipping", seq_id)
                    continue
                alerts, cached_dur = run_sequence(seq_id, cache_file, split_name)
                dur = float(r.get("duration_seconds") or cached_dur)
                total_duration_sec += dur
                total_false_alarms += len(alerts)
                dump_alerts(split_name, r, alerts, is_fall=False)
                video_reports.append(
                    {
                        "sequence_id": seq_id,
                        "duration_seconds": round(dur, 2),
                        "false_alerts": len(alerts),
                    }
                )
                LOG.info("  %s: %d false alerts", seq_id, len(alerts))

            total_hours = total_duration_sec / 3600.0
            rate, ci_low, ci_high = compute_poisson_ci(total_false_alarms, total_hours)
            LOG.info(
                "Longform Split '%s': %d false alarms in %.2f hours -> %.3f alerts/h "
                "(95%% Poisson CI: [%.3f, %.3f])",
                split_name,
                total_false_alarms,
                total_hours,
                rate,
                ci_low,
                ci_high,
            )

            eval_results["splits"][split_name] = {
                "split_type": "continuous_longform",
                "split_role": split_role(split_name),
                # The deployed model trains on dev_longform, so its rate there is in-sample.
                "in_sample_for_model": split_role(split_name) == "development",
                "total_sequences": len(records),
                "total_hours": round(total_hours, 3),
                "total_false_alarms": total_false_alarms,
                "false_alarm_rate_per_hour": rate,
                "poisson_95_ci": [ci_low, ci_high],
                "videos": video_reports,
            }

        else:
            match_results: list[EventMatchResult] = []
            camera_keys: list[str] = []
            activity_buckets: dict[str, list[EventMatchResult]] = {}

            for r in records:
                seq_id = r["sequence_id"]
                cache_file = cache_dir / f"{seq_id}.npz"
                if not cache_file.is_file():
                    LOG.warning("Missing pose cache for %s, skipping", seq_id)
                    continue

                is_fall = bool(r.get("is_fall", False))
                alerts, cached_dur = run_sequence(seq_id, cache_file, split_name)
                gt = SequenceGroundTruth(
                    sequence_id=seq_id,
                    is_fall=is_fall,
                    fall_start_sec=r.get("fall_start_sec"),
                    fall_end_sec=r.get("fall_end_sec"),
                    lying_start_sec=r.get("lying_start_sec"),
                    total_duration_sec=float(r.get("duration_seconds") or cached_dur),
                )
                res = matcher.match_sequence(gt, alerts)
                match_results.append(res)
                camera_keys.append(str(r.get("camera_id") or "unknown"))
                dump_alerts(split_name, r, alerts, is_fall=is_fall)
                activity_buckets.setdefault(
                    r.get("activity_label", "unknown"), []
                ).append(res)

            agg = aggregate_event_results(match_results)

            activity_breakdown: dict[str, Any] = {}
            for act_name, act_res_list in activity_buckets.items():
                act_agg = aggregate_event_results(act_res_list)
                is_fall_act = act_res_list[0].is_fall_gt
                activity_breakdown[act_name] = {
                    "total_sequences": len(act_res_list),
                    "is_fall_activity": is_fall_act,
                    "tp": act_agg.tp,
                    "fn": act_agg.fn,
                    "tn": act_agg.tn,
                    "fp_sequences": act_agg.fp,
                    "false_alerts_total": act_agg.false_alerts_total,
                    "recall": round(act_agg.recall, 4) if is_fall_act else None,
                    "specificity": (
                        round(act_agg.specificity, 4) if not is_fall_act else None
                    ),
                }

            LOG.info(
                "Split '%s': TP=%d FN=%d | ADL TN=%d FP=%d | false alerts=%d | Recall=%.4f "
                "Precision=%.4f Specificity=%.4f F1=%.4f | TTA p50=%s p95=%s",
                split_name,
                agg.tp,
                agg.fn,
                agg.tn,
                agg.fp,
                agg.false_alerts_total,
                agg.recall,
                agg.precision,
                agg.specificity,
                agg.f1_score,
                (
                    f"{agg.median_tta_sec:.2f}"
                    if agg.median_tta_sec is not None
                    else "N/A"
                ),
                f"{agg.p95_tta_sec:.2f}" if agg.p95_tta_sec is not None else "N/A",
            )

            tta = agg.median_tta_sec, agg.p90_tta_sec, agg.p95_tta_sec
            eval_results["splits"][split_name] = {
                "split_type": "short_clip_event_matched",
                "split_role": split_role(split_name),
                "total_sequences": len(records),
                "confusion_matrix": {
                    "tp": agg.tp,
                    "fn": agg.fn,
                    "tn_adl_sequences": agg.tn,
                    "fp_adl_sequences": agg.fp,
                    "false_alerts_total": agg.false_alerts_total,
                    "fall_sequences_with_false_alerts": agg.fall_sequences_with_false_alerts,
                },
                "metrics": {
                    "recall": round(agg.recall, 4),
                    "recall_95_ci": [round(x, 4) for x in agg.recall_ci_95],
                    "precision": round(agg.precision, 4),
                    "precision_95_ci": [round(x, 4) for x in agg.precision_ci_95],
                    "precision_definition": "tp / (tp + false_alerts_total)",
                    "specificity": round(agg.specificity, 4),
                    "specificity_95_ci": [round(x, 4) for x in agg.specificity_ci_95],
                    "f1_score": round(agg.f1_score, 4),
                },
                "time_to_alert_seconds": {
                    "median": round(tta[0], 3) if tta[0] is not None else None,
                    "p90": round(tta[1], 3) if tta[1] is not None else None,
                    "p95": round(tta[2], 3) if tta[2] is not None else None,
                    "all_tta_values": [round(t, 3) for t in agg.tta_values],
                },
                "activity_breakdown": activity_breakdown,
                "camera_breakdown": summarize_by_group(match_results, camera_keys),
            }

    # Deployment Gate Verification
    gate_eval: dict[str, Any] = {
        "gate_criteria": {
            "min_recall": 0.90,
            "min_precision": 0.85,
            "max_false_alarms_per_hour": 0.05,
            "max_p95_tta_seconds": 3.0,
        },
        "evaluations": {},
        "overall_gate_passed": False,
        "counts_as_final_claim": False,
    }

    all_passed = True
    for clip_split in ("test_a", "test_x", "test_b"):
        if clip_split not in eval_results["splits"]:
            continue
        m = eval_results["splits"][clip_split]["metrics"]
        p95 = eval_results["splits"][clip_split]["time_to_alert_seconds"]["p95"]
        role = split_role(clip_split)
        checks = {
            f"{clip_split}_recall_ge_0_90": (
                m["recall"],
                m["recall_95_ci"],
                m["recall"] >= 0.90,
            ),
            f"{clip_split}_precision_ge_0_85": (
                m["precision"],
                m["precision_95_ci"],
                m["precision"] >= 0.85,
            ),
            f"{clip_split}_p95_tta_le_3_0s": (
                p95,
                None,
                p95 is not None and p95 <= 3.0,
            ),
        }
        for name, (value, ci, passed) in checks.items():
            gate_eval["evaluations"][name] = {
                "value": value,
                "ci_95": ci,
                "passed": passed,
                "split_role": role,
            }
            all_passed = all_passed and passed

    for lf_split in sorted(LONGFORM_SPLITS):
        if lf_split in eval_results["splits"]:
            lf_rate = eval_results["splits"][lf_split]["false_alarm_rate_per_hour"]
            lf_ci = eval_results["splits"][lf_split]["poisson_95_ci"]
            lf_pass = lf_rate <= 0.05
            gate_eval["evaluations"][f"{lf_split}_fa_rate_le_0_05_per_h"] = {
                "rate_per_hour": lf_rate,
                "poisson_95_ci": lf_ci,
                "passed": lf_pass,
                "split_role": split_role(lf_split),
            }
            if not lf_pass:
                all_passed = False

    gate_eval["overall_gate_passed"] = all_passed and (
        len(gate_eval["evaluations"]) > 0
    )
    # Only a pass on every sealed final split, and nothing else, supports a held-out claim.
    evaluated = set(eval_results["splits"])
    gate_eval["counts_as_final_claim"] = bool(
        gate_eval["overall_gate_passed"]
        and evaluated
        and evaluated <= SEALED_SPLITS
        and {"test_b", "longform_adl_heldout"} <= evaluated
    )
    if evaluated & BURNED_SPLITS:
        gate_eval["note"] = (
            "Test-A/Test-X are burned (evaluated under several operating points) and "
            "are reported as development diagnostics (dev-2), not held-out results."
        )
    eval_results["gate_status"] = gate_eval

    def _json_default(obj: Any) -> Any:
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    # Save output JSON
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text(
        json.dumps(eval_results, indent=2, default=_json_default), encoding="utf-8"
    )
    LOG.info("Saved Event Evaluation Report to %s", output_report_path)

    # Save Alert Sidecar Dump
    sidecar_path = (
        output_report_path.parent / f"{output_report_path.stem}_alert_dump.json"
    )
    sidecar_data = {
        "report": output_report_path.name,
        "total_alerts": len(all_alert_events_dump),
        "alerts": all_alert_events_dump,
    }
    sidecar_path.write_text(
        json.dumps(sidecar_data, indent=2, default=_json_default), encoding="utf-8"
    )
    LOG.info(
        "Saved Alert Sidecar Dump (%d alerts) to %s",
        len(all_alert_events_dump),
        sidecar_path,
    )

    return eval_results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Event-Level Evaluator for Fall Detection Pipeline"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        help="Path to manifest JSON",
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
        help="Directory containing trained model weights",
    )
    parser.add_argument(
        "--split",
        action="append",
        dest="splits",
        help="Target split(s): 'dev2' (burned Test-A + Test-X diagnostics, default), "
        "'all_heldout' (sealed Test-B + longform_adl_heldout; needs --allow-sealed), "
        "'all', or a split name",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "docs" / "reports" / "V6_FINAL_EVALUATION.json",
        help="Path to save evaluation report JSON",
    )
    parser.add_argument(
        "--allow-sealed",
        "--allow-sealed-test-b",
        dest="allow_sealed",
        action="store_true",
        default=False,
        help="Permit evaluation of sealed final splits (Test-B, longform_adl_heldout); post-freeze only",
    )
    parser.add_argument(
        "--no-fixes",
        action="store_true",
        help="Disable root-cause fixes A/B/C (baseline V6.1 behaviour) at the calibrated thresholds",
    )
    args = parser.parse_args()

    manifest_file = Path(args.manifest).resolve()
    cache_dir = Path(args.cache_dir).resolve()
    models_dir = Path(args.models_dir).resolve()
    output_report = Path(args.output_report).resolve()

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    all_records = manifest_data.get("records", [])
    present_splits = sorted(
        list({r.get("split") for r in all_records if r.get("split")})
    )

    splits_arg = args.splits or ["dev2"]
    splits_to_eval: list[str] = []
    for s in splits_arg:
        if s in {"dev2", "all_heldout"}:
            group = BURNED_SPLITS if s == "dev2" else SEALED_SPLITS
            for h in sorted(group):
                if h in present_splits and h not in splits_to_eval:
                    splits_to_eval.append(h)
        elif s == "all":
            for p in present_splits:
                if (
                    p not in SEALED_SPLITS or args.allow_sealed
                ) and p not in splits_to_eval:
                    splits_to_eval.append(p)
        elif s in present_splits and s not in splits_to_eval:
            splits_to_eval.append(s)

    evaluate_pipeline_on_manifest(
        manifest_path=manifest_file,
        cache_dir=cache_dir,
        models_dir=models_dir,
        splits_to_evaluate=splits_to_eval,
        output_report_path=output_report,
        allow_sealed=args.allow_sealed,
        no_fixes=args.no_fixes,
    )


if __name__ == "__main__":
    main()
