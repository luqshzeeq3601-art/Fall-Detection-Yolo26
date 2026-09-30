"""Phase 11.8 / V6.1 Fold-Aware Event-Level Calibration.

Chooses post-processor thresholds (fall_trigger_threshold,
down_confirmation_threshold, min_down_sustain_seconds) on Dev + dev_longform using:
1. Out-of-fold M2 models: every sequence is scored by the CV fold model that never
   trained on its (source, subject) group (``models/v6_1_folds`` from train_v6.py).
2. The deployed V6.1 pipeline: signals come from ``FallEnginePipelineV61.compute_signals``
   and alerts from the same ``DecisionStageV61`` used at inference time.
3. EventMatcher scoring and the pre-declared gate:
   recall >= 0.90, precision >= 0.85, FA/h <= 0.05 (dev_longform), p95 TTA <= 3.0 s.

Selection: among points meeting every gate, maximise recall (then minimise FA/h).
If no point meets every gate, the point with the smallest normalised gate shortfall is
reported with ``feasible=False``; it is a diagnostic, not a passing operating point.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.cache.storage import load_keypoint_cache
from eldercare.fall_engine.evaluation.event_matching import (
    AlertEvent,
    EventMatcher,
    SequenceGroundTruth,
    aggregate_event_results,
    summarize_by_group,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.learned_classifier.training_v5 import sample_group_key
from eldercare.fall_engine.pipeline_v6_1 import (
    FallEnginePipelineV61,
    FrameSignalsV61,
    PipelineConfigV61,
    observations_from_cached_sequence,
    replay_signals,
)

try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

LOG = logging.getLogger("calibrate_v6_1")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
    force=True,
)

GATE = {
    "min_recall": 0.90,
    "min_precision": 0.85,
    "max_false_alarms_per_hour": 0.05,
    "max_p95_tta_seconds": 3.0,
}

TRIGGER_GRID = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
DOWN_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]
SUSTAIN_GRID = [0.15, 0.30, 0.45, 0.60, 0.90]
# (suppress_only_without_kinetic_peak, edge_check_bottom); (False, True) = no fixes
FIX_VARIANTS = [(False, True), (True, True), (False, False), (True, False)]


@dataclass
class SequenceSignals:
    """Out-of-fold signals for one Dev sequence."""

    record: dict[str, Any]
    fold: int
    duration_sec: float
    signals: list[FrameSignalsV61]


_SIGNAL_PIPELINES: dict[int, FallEnginePipelineV61] = {}
_SIGNAL_CTX: dict[str, Any] = {}


def _init_signal_worker(
    folds_dir: str, cache_dir: str, identity_jump_frac: float | None, stitch_tracks: bool
) -> None:
    import torch

    torch.set_num_threads(1)
    assignment = json.loads(
        (Path(folds_dir) / "fold_assignment.json").read_text(encoding="utf-8")
    )
    _SIGNAL_CTX.update(
        group_to_fold=assignment["group_to_fold"],
        cache_dir=Path(cache_dir),
        identity_jump_frac=identity_jump_frac,
        stitch_tracks=stitch_tracks,
    )
    for k in range(int(assignment["n_splits"])):
        model = TemporalSkeletonClassifierV5.load(Path(folds_dir) / f"m2_fold_{k}.pt")
        _SIGNAL_PIPELINES[k] = FallEnginePipelineV61(skeleton_classifier=model)


def _signals_for_record(
    r: dict[str, Any],
) -> tuple[SequenceSignals | None, dict[str, int]]:
    seq_id = r["sequence_id"]
    group = sample_group_key(r["source_dataset"], r["subject_id"])
    group_to_fold = _SIGNAL_CTX["group_to_fold"]
    if group not in group_to_fold:
        raise RuntimeError(
            f"Sequence {seq_id} (group {group}) has no CV fold; re-run train_v6.py."
        )
    stats: dict[str, int] = {}
    cache_file = _SIGNAL_CTX["cache_dir"] / f"{seq_id}.npz"
    if not cache_file.is_file():
        return None, stats

    fold = group_to_fold[group]
    pipeline = _SIGNAL_PIPELINES[fold]
    pipeline.reset()
    seq = load_keypoint_cache(cache_file)
    observations = observations_from_cached_sequence(
        seq,
        seq_id,
        max_center_jump_frac=_SIGNAL_CTX["identity_jump_frac"],
        stats=stats,
        stitch_tracks=_SIGNAL_CTX["stitch_tracks"],
    )
    sigs = [pipeline.compute_signals(obs, keep_features=False) for obs in observations]
    duration = float(
        r.get("duration_seconds")
        or (seq.frames[-1].timestamp - seq.frames[0].timestamp if seq.frames else 0.0)
    )
    return (
        SequenceSignals(record=r, fold=fold, duration_sec=duration, signals=sigs),
        stats,
    )


def compute_oof_signals(
    records: list[dict[str, Any]],
    cache_dir: Path,
    folds_dir: Path,
    identity_jump_frac: float | None,
    workers: int,
    stitch_tracks: bool = False,
) -> tuple[list[SequenceSignals], dict[str, dict[str, int]]]:
    """Score each sequence with the fold model that did not train on its group."""
    out: list[SequenceSignals] = []
    split_stats: dict[str, dict[str, int]] = {}
    t0 = time.time()
    # Longest sequences first so the pool finishes evenly.
    ordered = sorted(records, key=lambda r: -float(r.get("duration_seconds") or 0.0))
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_signal_worker,
        initargs=(str(folds_dir), str(cache_dir), identity_jump_frac, stitch_tracks),
    ) as pool:
        for idx, (seq_sig, stats) in enumerate(
            pool.map(_signals_for_record, ordered, chunksize=1)
        ):
            r = ordered[idx]
            agg = split_stats.setdefault(
                r["split"], {"kept": 0, "dropped_identity_jumps": 0}
            )
            for k, v in stats.items():
                agg[k] += v
            if seq_sig is None:
                LOG.warning("Missing pose cache for %s, skipping", r["sequence_id"])
                continue
            out.append(seq_sig)
            if (idx + 1) % 50 == 0 or r.get("split") == "dev_longform":
                LOG.info(
                    "Signals %d/%d (%s) - %.0fs elapsed",
                    idx + 1,
                    len(ordered),
                    r["sequence_id"],
                    time.time() - t0,
                )
    return out, split_stats


_WORKER_SEQS: list[SequenceSignals] = []


def _init_worker(signals_path: str) -> None:
    global _WORKER_SEQS
    with open(signals_path, "rb") as fh:
        _WORKER_SEQS = pickle.load(fh)


def _gate_shortfall(
    recall: float, precision: float, fa_rate: float, p95: float | None
) -> float:
    """Normalised distance from the gate (0.0 means every criterion is met)."""
    shortfall = max(0.0, GATE["min_recall"] - recall) / GATE["min_recall"]
    shortfall += max(0.0, GATE["min_precision"] - precision) / GATE["min_precision"]
    if fa_rate > GATE["max_false_alarms_per_hour"]:
        shortfall += math.log10(fa_rate / GATE["max_false_alarms_per_hour"])
    if p95 is None:
        shortfall += 1.0
    elif p95 > GATE["max_p95_tta_seconds"]:
        shortfall += (p95 - GATE["max_p95_tta_seconds"]) / GATE["max_p95_tta_seconds"]
    return shortfall


def evaluate_grid_point(
    point: tuple[float, float, float, bool, bool],
) -> dict[str, Any]:
    """Replay the V6.1 decision stage over all OOF signals for one threshold triple."""
    p_trig, p_down, t_sust, fix_a, edge_bottom = point
    base = PipelineConfigV61()
    cfg = replace(
        base,
        suppress_only_without_kinetic_peak=fix_a,
        edge_check_bottom=edge_bottom,
        post_processor=replace(
            base.post_processor,
            fall_trigger_threshold=p_trig,
            down_confirmation_threshold=p_down,
            min_down_sustain_seconds=t_sust,
        ),
    )
    matcher = EventMatcher(early_tolerance_sec=1.0, late_tolerance_sec=3.0)

    match_results = []
    camera_keys: list[str] = []
    lf_alerts = 0
    lf_seconds = 0.0
    for s in _WORKER_SEQS:
        alert_ts = replay_signals(s.signals, cfg)
        r = s.record
        if r.get("split") == "dev_longform":
            lf_alerts += len(alert_ts)
            lf_seconds += s.duration_sec
            continue
        gt = SequenceGroundTruth(
            sequence_id=r["sequence_id"],
            is_fall=bool(r.get("is_fall", False)),
            fall_start_sec=r.get("fall_start_sec"),
            fall_end_sec=r.get("fall_end_sec"),
            lying_start_sec=r.get("lying_start_sec"),
            total_duration_sec=s.duration_sec,
        )
        alerts = [
            AlertEvent(timestamp_sec=t, frame_idx=-1, track_id=1) for t in alert_ts
        ]
        match_results.append(matcher.match_sequence(gt, alerts))
        camera_keys.append(f"{r['source_dataset']}:{r.get('camera_id') or 'unknown'}")

    agg = aggregate_event_results(match_results)
    lf_hours = lf_seconds / 3600.0
    fa_rate = lf_alerts / lf_hours if lf_hours > 0 else float("inf")
    p95 = agg.p95_tta_sec
    shortfall = _gate_shortfall(agg.recall, agg.precision, fa_rate, p95)
    per_camera = {
        cam: {k: m[k] for k in ("tp", "fn", "false_alerts_total", "recall", "precision")}
        for cam, m in summarize_by_group(match_results, camera_keys).items()
    }
    return {
        "fall_trigger_threshold": p_trig,
        "down_confirmation_threshold": p_down,
        "min_down_sustain_seconds": t_sust,
        "suppress_only_without_kinetic_peak": fix_a,
        "edge_check_bottom": edge_bottom,
        "oof_recall": round(agg.recall, 4),
        "oof_precision": round(agg.precision, 4),
        "oof_specificity": round(agg.specificity, 4),
        "oof_f1": round(agg.f1_score, 4),
        "oof_median_tta": (
            round(agg.median_tta_sec, 3) if agg.median_tta_sec is not None else None
        ),
        "oof_p95_tta": round(p95, 3) if p95 is not None else None,
        "oof_false_alerts_short_clips": agg.false_alerts_total,
        "dev_longform_fa_count": lf_alerts,
        "dev_longform_hours": round(lf_hours, 3),
        "dev_longform_fa_rate_per_hour": round(fa_rate, 4),
        "gate_shortfall": round(shortfall, 4),
        "meets_all_gates": shortfall == 0.0,
        "oof_per_camera": per_camera,
    }


def select_operating_point(grid: list[dict[str, Any]]) -> dict[str, Any]:
    """Max recall among fully feasible points; otherwise the smallest gate shortfall."""
    feasible = [g for g in grid if g["meets_all_gates"]]
    if feasible:
        best = max(
            feasible,
            key=lambda g: (
                g["oof_recall"],
                -g["dev_longform_fa_rate_per_hour"],
                g["oof_precision"],
            ),
        )
    else:
        best = min(
            grid,
            key=lambda g: (
                g["gate_shortfall"],
                -g["oof_recall"],
                g["dev_longform_fa_rate_per_hour"],
            ),
        )
    on_boundary = {
        "fall_trigger_threshold": best["fall_trigger_threshold"]
        in (TRIGGER_GRID[0], TRIGGER_GRID[-1]),
        "down_confirmation_threshold": best["down_confirmation_threshold"]
        in (DOWN_GRID[0], DOWN_GRID[-1]),
        "min_down_sustain_seconds": best["min_down_sustain_seconds"]
        in (SUSTAIN_GRID[0], SUSTAIN_GRID[-1]),
    }
    return {**best, "feasible": bool(feasible), "on_grid_boundary": on_boundary}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fold-aware V6.1 event-level calibration"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
    )
    parser.add_argument(
        "--cache-dir", type=Path, default=ROOT / "datasets" / "cache" / "poses"
    )
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "models" / "v6_calibration_grid.json",
    )
    parser.add_argument(
        "--reuse-signals",
        action="store_true",
        help="Reuse models/v6_1_folds/oof_signals.pkl instead of recomputing",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--identity-jump-frac",
        type=float,
        default=0.25,
        help="Drop frames whose bbox centre jumps more than this fraction of the image "
        "diagonal (untracked pose cache identity switches); <= 0 disables",
    )
    args = parser.parse_args()
    identity_jump_frac = (
        args.identity_jump_frac if args.identity_jump_frac > 0 else None
    )

    models_dir = args.models_dir.resolve()
    folds_dir = models_dir / "v6_1_folds"
    signals_path = folds_dir / "oof_signals.pkl"
    train_report = json.loads(
        (models_dir / "v6_training_report.json").read_text(encoding="utf-8")
    )
    stitch_tracks = bool(train_report.get("stitch_tracks", False))

    manifest_bytes = args.manifest.read_bytes()
    records = json.loads(manifest_bytes.decode("utf-8")).get("records", [])
    dev_records = [r for r in records if r.get("split") in {"dev", "dev_longform"}]
    LOG.info("Calibrating on %d Dev + dev_longform sequences.", len(dev_records))

    stats_path = folds_dir / "oof_signals_stats.json"
    if args.reuse_signals and signals_path.is_file():
        LOG.info("Reusing OOF signals from %s", signals_path)
        signal_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    else:
        seqs, split_stats = compute_oof_signals(
            dev_records,
            args.cache_dir.resolve(),
            folds_dir,
            identity_jump_frac,
            args.workers,
            stitch_tracks,
        )
        with open(signals_path, "wb") as fh:
            pickle.dump(seqs, fh, protocol=pickle.HIGHEST_PROTOCOL)
        signal_stats = {
            "identity_jump_frac": identity_jump_frac,
            "frames_by_split": split_stats,
        }
        stats_path.write_text(json.dumps(signal_stats, indent=2), encoding="utf-8")
        LOG.info("Saved OOF signals for %d sequences to %s", len(seqs), signals_path)
        LOG.info("Identity-jump filtering: %s", json.dumps(split_stats))

    points = [
        (trig, down, sust, fix_a, edge_bottom)
        for (fix_a, edge_bottom) in FIX_VARIANTS
        for trig, down, sust in product(TRIGGER_GRID, DOWN_GRID, SUSTAIN_GRID)
    ]
    LOG.info("Replaying %d grid points with %d workers...", len(points), args.workers)
    t0 = time.time()
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_init_worker,
        initargs=(str(signals_path),),
    ) as pool:
        grid = list(pool.map(evaluate_grid_point, points, chunksize=4))
    LOG.info("Grid replay finished in %.0fs", time.time() - t0)

    best = select_operating_point(grid)
    LOG.info("Selected operating point: %s", json.dumps(best))
    best_per_variant = {
        f"fix_a={fix_a},edge_check_bottom={edge_bottom}": select_operating_point(
            [
                g
                for g in grid
                if g["suppress_only_without_kinetic_peak"] == fix_a
                and g["edge_check_bottom"] == edge_bottom
            ]
        )
        for fix_a, edge_bottom in FIX_VARIANTS
    }
    for name, pt in best_per_variant.items():
        LOG.info(
            "%s -> recall=%.4f precision=%.4f FA/h=%.3f p95=%s feasible=%s",
            name,
            pt["oof_recall"],
            pt["oof_precision"],
            pt["dev_longform_fa_rate_per_hour"],
            pt["oof_p95_tta"],
            pt["feasible"],
        )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "out-of-fold M2 fold models + FallEnginePipelineV61 decision stage",
        "gate": GATE,
        "grid_axes": {
            "fall_trigger_threshold": TRIGGER_GRID,
            "down_confirmation_threshold": DOWN_GRID,
            "min_down_sustain_seconds": SUSTAIN_GRID,
            "fix_variants(suppress_only_without_kinetic_peak, edge_check_bottom)": FIX_VARIANTS,
        },
        "signal_stats": signal_stats,
        "best_per_fix_variant": best_per_variant,
        "total_combinations": len(points),
        "feasible_points": sum(1 for g in grid if g["meets_all_gates"]),
        "optimal_point": best,
        "grid": grid,
    }
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("Saved calibration grid report to %s", args.output_report)

    train_report_path = models_dir / "v6_training_report.json"
    tr = json.loads(train_report_path.read_text(encoding="utf-8"))
    tr["calibrated_post_processor"] = {
        "fall_trigger_threshold": best["fall_trigger_threshold"],
        "down_confirmation_threshold": best["down_confirmation_threshold"],
        "min_down_sustain_seconds": best["min_down_sustain_seconds"],
        "require_falling_motion": True,
        "suppress_until_upright": True,
        "suppress_only_without_kinetic_peak": best[
            "suppress_only_without_kinetic_peak"
        ],
        "edge_check_bottom": best["edge_check_bottom"],
        "identity_jump_frac": identity_jump_frac,
        "stitch_tracks": stitch_tracks,
        "calibration_method": report["method"],
    }
    tr["event_level_dev_metrics"] = best
    tr["dev_exit_criteria_met"] = bool(best["feasible"])
    train_report_path.write_text(json.dumps(tr, indent=2), encoding="utf-8")
    LOG.info(
        "Updated %s (dev_exit_criteria_met=%s)", train_report_path, best["feasible"]
    )


if __name__ == "__main__":
    main()
