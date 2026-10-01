"""Phase 1 diagnostic: where does the V6.1 decision stage lose falls, per camera?

Uses the out-of-fold signals written by ``calibrate_event_v6_1.py`` (Dev + dev_longform
only; no Test split is touched) and the calibrated operating point from
``v6_training_report.json``. Produces:

1. Stage funnel per camera: for every Dev fall, the furthest decision state reached
   inside the EventMatcher window, and the first stage that failed.
2. Signal statistics per camera inside the fall window (peak p_falling / p_fallen,
   floor-posture trust gates, heuristic suppressor activity, pose availability).
3. Annotation alignment: offset of the p_falling peak from the annotated fall start.
4. Single-gate counterfactuals: per-camera recall and dev_longform FA/h when one gate
   at a time is relaxed.
"""

from __future__ import annotations

import argparse
import json
import pickle
import statistics
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "src", ROOT / "scripts" / "dataset"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import calibrate_event_v6_1  # noqa: E402

from eldercare.fall_engine.evaluation.event_matching import (  # noqa: E402
    AlertEvent,
    EventMatcher,
    SequenceGroundTruth,
    aggregate_event_results,
    summarize_by_group,
)
from eldercare.fall_engine.pipeline_v6_1 import (  # noqa: E402
    DecisionStageV61,
    FrameSignalsV61,
    PipelineConfigV61,
    is_floor_posture,
    replay_signals,
)
from eldercare.fall_engine.state_machine.states import FallState  # noqa: E402

EARLY_TOL = 1.0
LATE_TOL = 3.0

# Furthest-state ordering used for the funnel.
# "no_trigger" is split afterwards into below-threshold vs. suppressed triggers.
STAGES = ("no_signal", "no_trigger", "no_low_posture", "no_sustain", "alert")
FUNNEL_STAGES = (
    "no_signal",
    "p_falling_below_trigger",
    "trigger_suppressed",
    "no_low_posture",
    "no_sustain",
    "alert",
)


def camera_key(record: dict[str, Any]) -> str:
    return f"{record['source_dataset']}:{record.get('camera_id') or 'unknown'}"


def fall_window(record: dict[str, Any]) -> tuple[float, float]:
    fall_start = record.get("fall_start_sec") or 0.0
    lying = record.get("lying_start_sec") or record.get("fall_end_sec") or (fall_start + 2.0)
    return fall_start - EARLY_TOL, lying + LATE_TOL


def load_oof_signals(path: Path) -> list[Any]:
    # The pickle was written from calibrate_event_v6_1 run as __main__.
    sys.modules["__main__"].SequenceSignals = calibrate_event_v6_1.SequenceSignals  # type: ignore[attr-defined]
    with open(path, "rb") as fh:
        return pickle.load(fh)


def build_config(cal: dict[str, Any]) -> PipelineConfigV61:
    base = PipelineConfigV61()
    return replace(
        base,
        suppress_only_without_kinetic_peak=bool(
            cal.get("suppress_only_without_kinetic_peak", False)
        ),
        edge_check_bottom=bool(cal.get("edge_check_bottom", True)),
        descent_low_posture=bool(cal.get("descent_low_posture", False)),
        post_processor=replace(
            base.post_processor,
            fall_trigger_threshold=cal["fall_trigger_threshold"],
            down_confirmation_threshold=cal["down_confirmation_threshold"],
            min_down_sustain_seconds=cal["min_down_sustain_seconds"],
            transition_max_window_sec=cal.get("transition_max_window_sec", 2.0),
            require_falling_motion=cal.get("require_falling_motion", True),
            suppress_until_upright=cal.get("suppress_until_upright", True),
        ),
    )


def trace_fall(
    signals: list[FrameSignalsV61], cfg: PipelineConfigV61, window: tuple[float, float]
) -> dict[str, Any]:
    """Replay the decision stage and record the furthest state reached in ``window``."""
    stage = DecisionStageV61(cfg)
    pp = cfg.post_processor
    w0, w1 = window
    furthest = 0
    suppressed_frames = 0
    alert_times: list[float] = []
    in_window = [s for s in signals if w0 <= s.timestamp <= w1]
    for sig in signals:
        state, event = stage.step(sig)
        if event is not None:
            alert_times.append(sig.timestamp)
        if not (w0 <= sig.timestamp <= w1):
            continue
        if sig.has_history:
            furthest = max(furthest, 1)
        candidate_like = sig.p_falling >= pp.fall_trigger_threshold
        if (
            sig.has_history
            and candidate_like
            and sig.heuristic_suppressed
            and state == FallState.NORMAL
        ):
            suppressed_frames += 1
        if state in (FallState.DESCENT_CANDIDATE, FallState.DOWN_CONFIRMING):
            furthest = max(furthest, 2 if state == FallState.DESCENT_CANDIDATE else 3)
        if event is not None:
            furthest = 4

    hist = [s for s in in_window if s.has_history]
    matched = any(w0 <= t <= w1 for t in alert_times)
    peak = max(hist, key=lambda s: s.p_falling) if hist else None
    stage_name = STAGES[furthest] if not matched else "alert"
    if stage_name == "no_trigger":
        max_pf = max((s.p_falling for s in hist), default=0.0)
        stage_name = (
            "p_falling_below_trigger"
            if max_pf < pp.fall_trigger_threshold
            else "trigger_suppressed"
        )
    return {
        "stage": stage_name,
        "alert_outside_window": bool(alert_times) and not matched,
        "suppressed_trigger_frames": suppressed_frames,
        "frames_in_window": len(in_window),
        "frames_with_history": len(hist),
        "max_p_falling": round(max((s.p_falling for s in hist), default=0.0), 4),
        "max_p_fallen": round(max((s.p_fallen for s in hist), default=0.0), 4),
        "peak_p_falling_time": peak.timestamp if peak else None,
        "frac_geometric_floor": _frac(hist, lambda s: s.geometric_floor),
        "frac_full_body": _frac(hist, lambda s: s.has_full_body),
        "frac_floor_trusted": _frac(hist, lambda s: is_floor_posture(s, cfg)),
        "frac_touches_edge": _frac(hist, lambda s: s.touches_bottom_edge or s.touches_other_edge),
        "frac_heuristic_suppressed": _frac(hist, lambda s: s.heuristic_suppressed),
    }


def _frac(items: list[FrameSignalsV61], pred: Any) -> float | None:
    if not items:
        return None
    return round(sum(1 for s in items if pred(s)) / len(items), 4)


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def evaluate_variant(
    seqs: list[Any],
    cfg: PipelineConfigV61,
    signal_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-camera event metrics and dev_longform FA/h for one config / signal patch."""
    matcher = EventMatcher(early_tolerance_sec=EARLY_TOL, late_tolerance_sec=LATE_TOL)
    results, keys = [], []
    lf_alerts, lf_sec = 0, 0.0
    for s in seqs:
        sigs = s.signals
        if signal_patch:
            sigs = [replace(x, **signal_patch) for x in sigs]
        alert_ts = replay_signals(sigs, cfg)
        r = s.record
        if r.get("split") == "dev_longform":
            lf_alerts += len(alert_ts)
            lf_sec += s.duration_sec
            continue
        gt = SequenceGroundTruth(
            sequence_id=r["sequence_id"],
            is_fall=bool(r.get("is_fall", False)),
            fall_start_sec=r.get("fall_start_sec"),
            fall_end_sec=r.get("fall_end_sec"),
            lying_start_sec=r.get("lying_start_sec"),
            total_duration_sec=s.duration_sec,
        )
        alerts = [AlertEvent(timestamp_sec=t, frame_idx=-1, track_id=1) for t in alert_ts]
        results.append(matcher.match_sequence(gt, alerts))
        keys.append(camera_key(r))
    agg = aggregate_event_results(results)
    per_cam = summarize_by_group(results, keys)
    lf_hours = lf_sec / 3600.0
    return {
        "overall_recall": round(agg.recall, 4),
        "overall_precision": round(agg.precision, 4),
        "short_clip_false_alerts": agg.false_alerts_total,
        "dev_longform_fa_per_hour": round(lf_alerts / lf_hours, 3) if lf_hours else None,
        "per_camera": {
            k: {f: v[f] for f in ("tp", "fn", "false_alerts_total", "recall", "precision")}
            for k, v in per_cam.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="V6.1 decision-stage funnel diagnostic")
    parser.add_argument("--models-dir", type=Path, default=ROOT / "models" / "v6_1_phase0")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "docs" / "reports" / "V6_1_PHASE1_FUNNEL.json",
    )
    args = parser.parse_args()

    tr = json.loads((args.models_dir / "v6_training_report.json").read_text(encoding="utf-8"))
    cal = tr["calibrated_post_processor"]
    cfg = build_config(cal)
    seqs = load_oof_signals(args.models_dir / "v6_1_folds" / "oof_signals.pkl")
    if any(s.record.get("split") not in {"dev", "dev_longform"} for s in seqs):
        raise RuntimeError("OOF signal cache contains non-development splits.")

    falls = [s for s in seqs if s.record.get("split") == "dev" and s.record.get("is_fall")]
    per_seq: list[dict[str, Any]] = []
    for s in falls:
        r = s.record
        w = fall_window(r)
        t = trace_fall(s.signals, cfg, w)
        peak_t = t.pop("peak_p_falling_time")
        per_seq.append(
            {
                "sequence_id": r["sequence_id"],
                "camera": camera_key(r),
                "activity": r.get("activity_label"),
                "peak_offset_from_fall_start_sec": (
                    round(peak_t - (r.get("fall_start_sec") or 0.0), 3)
                    if peak_t is not None
                    else None
                ),
                **t,
            }
        )

    funnel: dict[str, Any] = {}
    for cam in sorted({x["camera"] for x in per_seq}):
        rows = [x for x in per_seq if x["camera"] == cam]
        counts = Counter(x["stage"] for x in rows)
        by_activity: dict[str, dict[str, int]] = {}
        for x in rows:
            by_activity.setdefault(x["activity"], Counter())[x["stage"]] += 1
        missed = [x for x in rows if x["stage"] != "alert"]
        funnel[cam] = {
            "fall_sequences": len(rows),
            "furthest_stage_counts": {st: counts.get(st, 0) for st in FUNNEL_STAGES},
            "missed_with_alert_outside_window": sum(1 for x in missed if x["alert_outside_window"]),
            "missed_with_suppressed_trigger": sum(
                1 for x in missed if x["suppressed_trigger_frames"] > 0
            ),
            "by_activity": {a: dict(c) for a, c in sorted(by_activity.items())},
            "median_max_p_falling": _median([x["max_p_falling"] for x in rows]),
            "median_max_p_fallen": _median([x["max_p_fallen"] for x in rows]),
            "median_frac_geometric_floor": _median(
                [x["frac_geometric_floor"] for x in rows if x["frac_geometric_floor"] is not None]
            ),
            "median_frac_full_body": _median(
                [x["frac_full_body"] for x in rows if x["frac_full_body"] is not None]
            ),
            "median_frac_floor_trusted": _median(
                [x["frac_floor_trusted"] for x in rows if x["frac_floor_trusted"] is not None]
            ),
            "median_frac_touches_edge": _median(
                [x["frac_touches_edge"] for x in rows if x["frac_touches_edge"] is not None]
            ),
            "median_frac_heuristic_suppressed": _median(
                [
                    x["frac_heuristic_suppressed"]
                    for x in rows
                    if x["frac_heuristic_suppressed"] is not None
                ]
            ),
            "median_frames_with_history": _median([x["frames_with_history"] for x in rows]),
            "peak_offset_sec": {
                "median": _median(
                    [
                        x["peak_offset_from_fall_start_sec"]
                        for x in rows
                        if x["peak_offset_from_fall_start_sec"] is not None
                    ]
                ),
            },
            "p_falling_ge_trigger_fraction": round(
                sum(1 for x in rows if x["max_p_falling"] >= cal["fall_trigger_threshold"])
                / max(1, len(rows)),
                4,
            ),
        }

    pp = cfg.post_processor
    variants: dict[str, tuple[PipelineConfigV61, dict[str, Any] | None]] = {
        "calibrated": (cfg, None),
        "no_require_falling_motion": (
            replace(cfg, post_processor=replace(pp, require_falling_motion=False)),
            None,
        ),
        "trigger_0.35": (
            replace(cfg, post_processor=replace(pp, fall_trigger_threshold=0.35)),
            None,
        ),
        "down_0.35": (
            replace(cfg, post_processor=replace(pp, down_confirmation_threshold=0.35)),
            None,
        ),
        "sustain_0.3s": (
            replace(cfg, post_processor=replace(pp, min_down_sustain_seconds=0.3)),
            None,
        ),
        "transition_window_3s": (
            replace(cfg, post_processor=replace(pp, transition_max_window_sec=3.0)),
            None,
        ),
        "no_heuristic_suppressor": (cfg, {"heuristic_suppressed": False}),
        "floor_trust_gates_off": (
            cfg,
            {"has_full_body": True, "touches_bottom_edge": False, "touches_other_edge": False},
        ),
        # Decision-stage ceiling: every gate relaxed at once. If recall stays low here,
        # the classifier signals themselves (not the gating) are the bottleneck.
        "all_gates_relaxed": (
            replace(
                cfg,
                post_processor=replace(
                    pp,
                    require_falling_motion=False,
                    fall_trigger_threshold=0.35,
                    down_confirmation_threshold=0.35,
                    min_down_sustain_seconds=0.3,
                    transition_max_window_sec=3.0,
                ),
            ),
            {
                "heuristic_suppressed": False,
                "has_full_body": True,
                "touches_bottom_edge": False,
                "touches_other_edge": False,
            },
        ),
    }
    counterfactuals = {
        name: evaluate_variant(seqs, vcfg, patch) for name, (vcfg, patch) in variants.items()
    }

    report = {
        "phase": "Phase 1 / V6.1 decision-stage funnel",
        "data": "out-of-fold Dev + dev_longform signals (no Test split used)",
        "models_dir": str(args.models_dir.resolve().relative_to(ROOT)),
        "operating_point": {
            k: cal[k]
            for k in (
                "fall_trigger_threshold",
                "down_confirmation_threshold",
                "min_down_sustain_seconds",
                "require_falling_motion",
                "suppress_only_without_kinetic_peak",
                "edge_check_bottom",
            )
        },
        "funnel_per_camera": funnel,
        "counterfactuals": counterfactuals,
        "per_sequence": per_seq,
    }
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"funnel_per_camera": funnel, "counterfactuals": counterfactuals}, indent=1))


if __name__ == "__main__":
    main()
