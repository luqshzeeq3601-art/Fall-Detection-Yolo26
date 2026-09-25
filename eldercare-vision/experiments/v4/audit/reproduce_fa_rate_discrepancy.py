"""P11.7-001 — Reproduce the P11.6-006 false-alert-rate discrepancy.

Replays the frozen V3 holdout evaluation in memory, using the same generator, config and
model as ``experiments/v3/holdout/run_holdout_evaluation_v3.py``. It shows where the reported
0.301 false alerts / camera-hour comes from and how much long-form footage was actually
processed.

Read-only with respect to all V3 artifacts. Writes only
``experiments/v4/audit/P11.7-001-fa-rate-reproduction.json``.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.learned_classifier.classifier_v3 import (  # noqa: E402
    LogisticClassifierV3,
)
from eldercare.fall_engine.state_machine_v3.config_v3 import (  # noqa: E402
    FallStateMachineConfigV3,
)
from eldercare.fall_engine.state_machine_v3.machine_v3 import (  # noqa: E402
    TrackFallStateMachineV3,
)

HOLDOUT_RUNNER = ROOT / "experiments" / "v3" / "holdout" / "run_holdout_evaluation_v3.py"
MANIFEST = ROOT / "datasets" / "manifests" / "v3_deployment_holdout_manifest.csv"
MODEL = ROOT / "models" / "temporal_fall_classifier_v3.json"
logger = logging.getLogger("reproduce_fa_rate_discrepancy")
OUTPUT = Path(__file__).resolve().parent / "P11.7-001-fa-rate-reproduction.json"


def _load_holdout_runner() -> Any:
    spec = importlib.util.spec_from_file_location("run_holdout_evaluation_v3", HOLDOUT_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v3_holdout_config() -> FallStateMachineConfigV3:
    # Identical to run_holdout_evaluation_v3.py:202-214.
    return FallStateMachineConfigV3(
        feature_window_sec=1.0,
        descent_velocity_threshold=0.35,
        peak_descent_velocity_threshold=0.70,
        descent_aspect_ratio_drop=-0.25,
        fallen_aspect_ratio_max=1.10,
        fallen_torso_angle_max_deg=40.0,
        min_down_confirming_frames=3,
        down_confirmation_sec=0.6,
        use_angular_velocity=True,
        angular_velocity_descent_threshold=30.0,
        enable_track_stitching=True,
    )


def reproduce() -> dict[str, Any]:
    runner = _load_holdout_runner()
    clf = LogisticClassifierV3.load(MODEL)
    config = _v3_holdout_config()
    with open(MANIFEST, encoding="utf-8") as f:
        records = list(csv.DictReader(f))

    false_positives: list[dict[str, Any]] = []
    streams: list[dict[str, Any]] = []
    tp = fn = tn_short = 0
    short_adl_count = 0
    declared_non_fall_hours = 0.0

    for rec in records:
        is_fall = int(rec["is_fall"]) == 1
        dur_hrs = float(rec.get("duration_hours") or 0.0)
        if not is_fall:
            declared_non_fall_hours += dur_hrs or float(rec["duration_seconds"]) / 3600.0

        obs = runner._generate_holdout_observations(rec)
        sm = TrackFallStateMachineV3(
            camera_id=rec["camera_id"], track_id=1, config=config, classifier=clf
        )
        history: list[Any] = []
        event = None
        for o in obs:
            history.append(o)
            _, ev = sm.update(history)
            if ev is not None:
                event = ev
                break

        fps = float(rec["fps"])
        is_stream = dur_hrs > 0 and not is_fall
        if is_stream:
            streams.append(
                {
                    "sample_id": rec["sample_id"],
                    "declared_hours": dur_hrs,
                    "frames_processed": len(obs),
                    "seconds_processed": round(len(obs) / fps, 3),
                    "alert": event is not None,
                }
            )
        elif is_fall:
            tp += event is not None
            fn += event is None
        else:
            short_adl_count += 1
            if event is not None:
                false_positives.append(
                    {
                        "sample_id": rec["sample_id"],
                        "activity": rec["activity"],
                        "lighting": rec["lighting"],
                        "clip_seconds": float(rec["duration_seconds"]),
                        "event_confidence": round(event.confidence, 4),
                    }
                )
            else:
                tn_short += 1

    fp = len(false_positives)
    stream_fp = sum(s["alert"] for s in streams)
    processed_stream_seconds = sum(s["seconds_processed"] for s in streams)
    declared_stream_hours = sum(s["declared_hours"] for s in streams)
    return {
        "task_id": "P11.7-001",
        "purpose": "Resolve P11.6-006 0.301 FA/h vs '0 false alerts in 26.5 h'",
        "inputs": {
            "generator": str(HOLDOUT_RUNNER.relative_to(ROOT)).replace("\\", "/"),
            "manifest": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "model": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
        },
        "fall_clips": {"tp": tp, "fn": fn},
        "short_adl_clips": {
            "count": short_adl_count,
            "false_positives": fp,
            "true_negatives": tn_short,
            "false_positive_rate": round(fp / short_adl_count, 4) if short_adl_count else None,
            "false_positive_samples": false_positives,
        },
        "long_form_streams": {
            "count": len(streams),
            "declared_hours": round(declared_stream_hours, 2),
            "seconds_actually_processed": round(processed_stream_seconds, 3),
            "alerts": stream_fp,
            "per_stream": streams,
        },
        "reported_metric_reconstruction": {
            "numerator_false_positive_clips": fp,
            "denominator_declared_non_fall_hours": round(declared_non_fall_hours, 4),
            "reported_false_alerts_per_camera_hour": round(fp / declared_non_fall_hours, 4),
        },
        "conclusion": (
            "The 0.301/h figure divides short-clip false positives by declared long-form hours "
            "(unit mismatch). The long-form streams were rendered as 12 s of synthetic walking "
            "each, so the '0 false alerts in 26.5 camera-hours' claim was never measured. True "
            "long-form false alerts per camera-hour is UNMEASURED."
        ),
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger.setLevel(logging.INFO)
    result = reproduce()
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rec = result["reported_metric_reconstruction"]
    lf = result["long_form_streams"]
    logger.info(
        "FP clips=%d / declared hours=%.4f -> %.4f/h; long-form processed %.1f s of %.2f h",
        rec["numerator_false_positive_clips"],
        rec["denominator_declared_non_fall_hours"],
        rec["reported_false_alerts_per_camera_hour"],
        lf["seconds_actually_processed"],
        lf["declared_hours"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
