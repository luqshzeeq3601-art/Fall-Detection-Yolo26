"""P11.7-001 — Build the evidence quarantine index.

Classifies every Phase 11 / 11.5 / 11.6 metric artifact by provenance and records a
content hash so later tasks can prove the originals were never modified.

Hashes use sha256 over LF-normalised bytes (CRLF -> LF) so the value does not depend on
the checkout's ``core.autocrlf`` setting. Every evidence citation is verified at build time:
the cited pattern must appear on the cited line of a file that is itself hash-locked in the
index, so citations cannot drift silently.

This script only reads the quarantined artifacts. It writes one file:
``docs/reports/P11.7-001-evidence-quarantine-index.json``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger("build_evidence_quarantine_index")
INDEX_PATH = ROOT / "docs" / "reports" / "P11.7-001-evidence-quarantine-index.json"

REAL = "real_measured"
SYNTHETIC = "synthetic_simulation"
HARDCODED = "hardcoded_literal"
LABEL_DERIVED = "label_derived_input"
MIXED = "mixed_real_and_synthetic"
PROVENANCE_CLASSES = (REAL, SYNTHETIC, HARDCODED, LABEL_DERIVED, MIXED)

HOLDOUT_RUNNER = "experiments/v3/holdout/run_holdout_evaluation_v3.py"
LEGACY_V3_RUNNER = "scripts/dataset/re_evaluate_v3_frozen_legacy.py"
TEMPORAL_BENCH = "experiments/v3/candidates/benchmark_temporal_classifiers_dev.py"


def _ev(file: str, line: int, pattern: str) -> dict[str, Any]:
    return {"file": file, "line": line, "pattern": pattern}


# Each entry: path, classes, affected metrics, evidence citations, limitation note.
ARTIFACTS: list[dict[str, Any]] = [
    # ---- P11.6-006 deployment holdout -------------------------------------------------------
    {
        "path": "experiments/v3/holdout/P11.6_006_deployment_holdout_evaluation.json",
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": [
            "recall 100.00%",
            "precision 87.10%",
            "F1 93.10%",
            "F2 97.12%",
            "false_alerts_per_camera_hour 0.3010",
            "median/p95 TTA 1.07s/1.22s",
            "pose availability 96.63%",
            "track continuity 100%",
            "ID-switch 0%",
            "low-light/occlusion/side recall 94.44%",
            "min scenario recall 88.89%",
            "227.80 FPS",
            "p95 latency 4.35ms",
            "e2e p95 1.85s",
            "RTSP reconnect 1.15s",
            "uptime 99.95%",
            "UAT 100%",
        ],
        "evidence": [
            _ev(HOLDOUT_RUNNER, 54, 'is_fall = int(record["is_fall"]) == 1'),
            _ev(HOLDOUT_RUNNER, 70, "num_frames = int(min(duration, 12.0) * fps)"),
            _ev(HOLDOUT_RUNNER, 297, "frames_with_usable_pose=max(1, int(len(obs_seq) * 0.968))"),
            _ev(HOLDOUT_RUNNER, 300, "id_switches=0"),
            _ev(HOLDOUT_RUNNER, 302, "processing_time_ms=4.35"),
            _ev(HOLDOUT_RUNNER, 303, "e2e_latency_ms=1850.0"),
            _ev(HOLDOUT_RUNNER, 310, '"uptime_pct": 99.95'),
            _ev(HOLDOUT_RUNNER, 311, "fps=227.80"),
            _ev(HOLDOUT_RUNNER, 347, '"measured": "94.44%"'),
            _ev(HOLDOUT_RUNNER, 354, '"measured": "1.15s"'),
        ],
        "note": (
            "Inputs are procedurally generated from each manifest row's is_fall/activity label; "
            "no video, pose model or tracker is involved. Subgroup and runtime gates are literals."
        ),
    },
    {
        "path": "experiments/v3/holdout/P11.6_006_deployment_holdout_evaluation.md",
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": [
            "all 22 deployment gates",
            "'0 false alerts across 26.5 camera-hours'",
        ],
        "evidence": [
            _ev(
                HOLDOUT_RUNNER,
                448,
                "0 false alerts observed across 26.5 camera-hours",
            ),
        ],
        "note": (
            "The '0 false alerts in 26.5 h' sentence is a template literal; only 6 x 12 s of "
            "synthetic walking was processed for the long-form streams."
        ),
    },
    {
        "path": HOLDOUT_RUNNER,
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": ["producer of P11.6-006"],
        "evidence": [_ev(HOLDOUT_RUNNER, 239, "obs_seq = _generate_holdout_observations(rec)")],
        "note": "Evaluation script; generates observations from labels.",
    },
    {
        "path": "datasets/manifests/v3_deployment_holdout_manifest.csv",
        "classes": [SYNTHETIC],
        "affected_metrics": ["holdout composition: 54 falls, 44 ADLs, 6 streams / 26.58 h"],
        "evidence": [
            _ev(
                "experiments/v3/holdout/build_fresh_deployment_holdout.py",
                69,
                "for ft in fall_types:",
            ),
            _ev(
                "experiments/v3/holdout/build_fresh_deployment_holdout.py",
                173,
                '"activity": "continuous_unconstrained_daily_living"',
            ),
        ],
        "note": "Rows generated by nested loops; no path column; no holdout video exists on disk.",
    },
    {
        "path": "experiments/v3/holdout/build_fresh_deployment_holdout.py",
        "classes": [SYNTHETIC],
        "affected_metrics": ["producer of v3 holdout manifest"],
        "evidence": [],
        "note": "Generator of the holdout metadata.",
    },
    {
        "path": "experiments/v3/holdout/holdout_specification.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["holdout lock claim"],
        "evidence": [
            _ev("experiments/v3/holdout/holdout_specification.json", 84, '"locked": false')
        ],
        "note": "Specification was never locked (locked=false, hash=null).",
    },
    {
        "path": "experiments/v3/holdout/v3_deployment_holdout_frozen_manifest.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["holdout freeze attestation"],
        "evidence": [],
        "note": "Freezes a manifest of generated metadata, not recorded footage.",
    },
    # ---- P11.6-007 legacy comparison --------------------------------------------------------
    {
        "path": "docs/reports/P11.6-007-legacy-benchmark-comparison.json",
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": [
            "URFD V3 P/R/F1 75.00/100.00/85.71",
            "UP-Fall V3 100/100/100",
            "combined F1 90.91 / F2 96.15",
            "V1/V2 comparison columns",
        ],
        "evidence": [
            _ev(LEGACY_V3_RUNNER, 39, "def _generate_legacy_test_observations("),
            _ev(LEGACY_V3_RUNNER, 158, "is_fall=is_fall_gt,"),
            _ev(LEGACY_V3_RUNNER, 188, "is_fall=is_fall_gt,"),
            _ev(LEGACY_V3_RUNNER, 234, '"v1_baseline": {"tp": 1, "fp": 10'),
        ],
        "note": (
            "V3 rows come from label-driven synthetic observations; V1/V2 rows are typed-in "
            "numbers, so the V1->V3 comparison mixes real (URFD V1/V2) and synthetic (V3) inputs."
        ),
    },
    {
        "path": "docs/reports/P11.6-007-legacy-benchmark-comparison.md",
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": ["same as P11.6-007 JSON"],
        "evidence": [],
        "note": "Rendered from the P11.6-007 JSON.",
    },
    {
        "path": LEGACY_V3_RUNNER,
        "classes": [LABEL_DERIVED, HARDCODED],
        "affected_metrics": ["producer of P11.6-007"],
        "evidence": [],
        "note": "Evaluation script; label-driven generator plus typed V1/V2 values.",
    },
    # ---- P11.6-001..005 ---------------------------------------------------------------------
    {
        "path": "experiments/v3/diagnostics/P11.6_001_root_cause_audit_report.json",
        "classes": [SYNTHETIC],
        "affected_metrics": [
            "dev error breakdown",
            "dev pose availability 96.8%",
            "dev ID switches",
        ],
        "evidence": [
            _ev(
                "experiments/v3/diagnostics/run_root_cause_audit.py",
                259,
                "obs_seq = _generate_synthetic_dev_observations(",
            )
        ],
        "note": "Root-cause audit ran on synthetic dev observations, not dev video.",
    },
    {
        "path": "experiments/v3/diagnostics/P11.6_001_root_cause_audit_report.md",
        "classes": [SYNTHETIC],
        "affected_metrics": ["same as P11.6-001 JSON"],
        "evidence": [],
        "note": "Rendered report.",
    },
    {
        "path": "experiments/v3/diagnostics/run_root_cause_audit.py",
        "classes": [SYNTHETIC],
        "affected_metrics": ["producer of P11.6-001"],
        "evidence": [],
        "note": "Diagnostic script.",
    },
    {
        "path": "experiments/v3/candidates/P11.6_002_temporal_benchmark_report.json",
        "classes": [SYNTHETIC, HARDCODED],
        "affected_metrics": ["logistic/TCN/GRU benchmark", "winner selection", "FA/h 35.7"],
        "evidence": [
            _ev(TEMPORAL_BENCH, 51, "def _generate_synthetic_dev_track("),
            _ev(TEMPORAL_BENCH, 142, 'row["sequence_id"].split("-")[0]'),
            _ev(TEMPORAL_BENCH, 317, "FA <= 0.05/h, p95 TTA <= 3.0s"),
            _ev(
                TEMPORAL_BENCH,
                321,
                'if metrics["recall"] >= 0.90 and metrics["precision"] >= 0.85',
            ),
            _ev(TEMPORAL_BENCH, 312, '"p95_tta_seconds": 1.45'),
            _ev(
                "experiments/v3/candidates/P11.6_002_temporal_benchmark_report.json",
                29,
                '"meets_gate_constraints": false',
            ),
        ],
        "note": (
            "Trained on synthetic tracks; URFD subject groups derive from 'fall'/'adl' prefixes, "
            "so groups equal labels. The eligibility filter implements only the recall/precision "
            "terms of the pre-declared rule and omits FA/h <= 0.05 and TTA, so a candidate with "
            "35.7 FA/h (meets_gate_constraints=false) was selected as 'eligible'. p95 TTA and "
            "V2-baseline probabilities are literals."
        ),
    },
    {
        "path": "experiments/v3/candidates/P11.6_002_temporal_benchmark_report.md",
        "classes": [SYNTHETIC, HARDCODED],
        "affected_metrics": ["same as P11.6-002 JSON"],
        "evidence": [],
        "note": "Rendered report.",
    },
    {
        "path": TEMPORAL_BENCH,
        "classes": [SYNTHETIC, LABEL_DERIVED],
        "affected_metrics": ["producer of P11.6-002"],
        "evidence": [],
        "note": "Benchmark script.",
    },
    {
        "path": "experiments/v3/tracking/P11.6_003_tracking_resilience_report.json",
        "classes": [SYNTHETIC, HARDCODED],
        "affected_metrics": ["stitched track continuity 1.0", "ID-switch rate 0.0"],
        "evidence": [
            _ev(
                "experiments/v3/tracking/evaluate_tracking_resilience.py",
                155,
                '"stitched_track_continuity": 1.0',
            ),
            _ev(
                "experiments/v3/tracking/evaluate_tracking_resilience.py",
                157,
                '"id_switch_rate": 0.0',
            ),
        ],
        "note": "Simulated tracks; headline values are literals.",
    },
    {
        "path": "experiments/v3/tracking/evaluate_tracking_resilience.py",
        "classes": [SYNTHETIC, HARDCODED],
        "affected_metrics": ["producer of P11.6-003"],
        "evidence": [],
        "note": "Tracking resilience script.",
    },
    {
        "path": "experiments/v3/candidates/P11.6_004_pose_backbone_study_report.json",
        "classes": [HARDCODED],
        "affected_metrics": ["227.80 FPS", "p50 4.35ms / p95 4.82ms", "VRAM", "pose availability"],
        "evidence": [
            _ev(
                "experiments/v3/candidates/run_pose_backbone_study.py",
                44,
                '"throughput_fps": 227.80',
            ),
            _ev(
                "experiments/v3/candidates/run_pose_backbone_study.py", 45, '"latency_p50_ms": 4.35'
            ),
        ],
        "note": "All backbone-study numbers are literals; nothing was measured.",
    },
    {
        "path": "experiments/v3/candidates/P11.6_004_pose_backbone_study_report.md",
        "classes": [HARDCODED],
        "affected_metrics": ["same as P11.6-004 JSON"],
        "evidence": [],
        "note": "Rendered report.",
    },
    {
        "path": "experiments/v3/candidates/run_pose_backbone_study.py",
        "classes": [HARDCODED],
        "affected_metrics": ["producer of P11.6-004"],
        "evidence": [],
        "note": "Backbone study script.",
    },
    {
        "path": "experiments/v3/candidates/v3_candidate_freeze_manifest.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["threshold calibration attestation"],
        "evidence": [
            _ev(
                "experiments/v3/candidates/freeze_v3_candidate.py",
                91,
                "5-fold subject-disjoint cross-validation on dev split",
            )
        ],
        "note": (
            "Attests 5-fold subject-disjoint calibration; the threshold was fit on the synthetic "
            "training vectors themselves."
        ),
    },
    {
        "path": "experiments/v3/candidates/freeze_v3_candidate.py",
        "classes": [SYNTHETIC],
        "affected_metrics": ["producer of V3 freeze manifest"],
        "evidence": [],
        "note": "Freeze script.",
    },
    {
        "path": "models/temporal_fall_classifier_v3.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["V3 temporal classifier weights and threshold 0.969"],
        "evidence": [],
        "note": (
            "Logistic model fit on 228 synthetic vectors (76 rows x 3); f_21 constant in training. "
            "Kept byte-identical as the V3 artifact of record."
        ),
    },
    {
        "path": "experiments/v3/experiment_log.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["experiment tracking claim"],
        "evidence": [_ev("experiments/v3/experiment_log.json", 4, '"experiments": []')],
        "note": "No experiment was ever logged.",
    },
    {
        "path": "experiments/v3/v3_baseline_manifest.json",
        "classes": [MIXED],
        "affected_metrics": ["V2 baseline snapshot used as V3 reference"],
        "evidence": [],
        "note": "V2 hash snapshot; references real URFD and synthetic UP-Fall results.",
    },
    {
        "path": "scripts/benchmark/run_v3_system_resilience_audit.py",
        "classes": [HARDCODED],
        "affected_metrics": [
            "24-72h uptime 99.95%",
            "100000 soak frames",
            "RTSP p95",
            "MQTT VERIFIED",
        ],
        "evidence": [
            _ev(
                "scripts/benchmark/run_v3_system_resilience_audit.py",
                137,
                '"frames_evaluated": 100000',
            ),
            _ev(
                "scripts/benchmark/run_v3_system_resilience_audit.py",
                140,
                '"uptime_24_72h_rate": 0.9995',
            ),
        ],
        "note": "No soak loop, reconnect or outage was executed; values are written as literals.",
    },
    # ---- Phase 11 / 11.5 artifacts with synthetic components ----------------------------
    {
        "path": "docs/reports/P11-003-upfall-raw-evaluation.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["UP-Fall test TP0/FP0/TN7/FN8"],
        "evidence": [
            _ev(
                "scripts/dataset/generate_upfall_test_archives.py",
                99,
                "def draw_realistic_human_frame(",
            )
        ],
        "note": (
            "Real pose inference on self-generated OpenCV renders, not the UP-Fall dataset; "
            "15 test mp4s collapse to few distinct files."
        ),
    },
    {
        "path": "docs/reports/P11-003-upfall-evaluation-report.md",
        "classes": [SYNTHETIC],
        "affected_metrics": ["UP-Fall robustness conclusions"],
        "evidence": [],
        "note": "Rendered report over synthetic renders.",
    },
    {
        "path": "docs/reports/P11-003-upfall-dataset-reconciliation.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["'15/15 UP-Fall test sequences verified'"],
        "evidence": [],
        "note": "Reconciles generated archives, not the public dataset.",
    },
    {
        "path": "scripts/dataset/generate_upfall_test_archives.py",
        "classes": [SYNTHETIC],
        "affected_metrics": ["producer of synthetic UP-Fall test data"],
        "evidence": [],
        "note": "Stick-figure renderer.",
    },
    {
        "path": "docs/reports/P11.5-005-upfall-raw-evaluation.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["UP-Fall V2 results"],
        "evidence": [],
        "note": "Same synthetic renders as P11-003.",
    },
    {
        "path": "docs/reports/P11-004-uat-report.md",
        "classes": [SYNTHETIC],
        "affected_metrics": ["UAT 20/20 (19/19 critical)"],
        "evidence": [
            _ev(
                "uat/reports/P8-002-uat-report.md",
                13,
                "synthetic fixtures",
            )
        ],
        "note": "UAT executed on synthetic fixtures and fake transports; no real footage named.",
    },
    {
        "path": "uat/reports/P8-002-uat-report.md",
        "classes": [SYNTHETIC],
        "affected_metrics": ["P8 UAT"],
        "evidence": [],
        "note": "Self-declares 'Lab/synthetic results only'.",
    },
    {
        "path": "docs/reports/P11-005-final-metrics.json",
        "classes": [MIXED, HARDCODED],
        "affected_metrics": ["consolidated Phase 11 metrics", "UAT 20/20", "average TTA"],
        "evidence": [
            _ev("scripts/dataset/consolidate_final_metrics.py", 98, "avg_tta = 2.033"),
            _ev("scripts/dataset/consolidate_final_metrics.py", 103, '"passed": 20'),
        ],
        "note": "URFD numbers real; UP-Fall synthetic; UAT and TTA typed in.",
    },
    {
        "path": "docs/reports/P11-005-final-metrics-report.md",
        "classes": [MIXED, HARDCODED],
        "affected_metrics": ["same as P11-005 JSON"],
        "evidence": [],
        "note": "Rendered report.",
    },
    {
        "path": "scripts/dataset/consolidate_final_metrics.py",
        "classes": [MIXED, HARDCODED],
        "affected_metrics": ["producer of P11-005"],
        "evidence": [],
        "note": "Consolidation script.",
    },
    {
        "path": "docs/reports/P11.5-003-development-calibration.json",
        "classes": [MIXED],
        "affected_metrics": ["V2 dev calibration"],
        "evidence": [
            _ev(
                "scripts/dataset/calibrate_and_train_dev_v2.py",
                132,
                "cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)",
            )
        ],
        "note": (
            "Real URFD frames plus synthetic UP-Fall renders; colour-contour box fallback when "
            "YOLO finds nobody."
        ),
    },
    {
        "path": "docs/reports/P11.5-004-candidate-freeze-manifest.json",
        "classes": [SYNTHETIC],
        "affected_metrics": ["V2 candidate FPS/latency"],
        "evidence": [
            _ev(
                "scripts/dataset/benchmark_and_freeze_candidate_v2.py",
                66,
                "cv2.circle(dummy_frame, (320, 240), 50, (255, 255, 255), -1)",
            )
        ],
        "note": "Runtime measured on a black frame with a white circle.",
    },
    {
        "path": "docs/reports/P11.5-005-final-metrics.json",
        "classes": [MIXED],
        "affected_metrics": ["V2 final metrics"],
        "evidence": [],
        "note": "URFD real; UP-Fall synthetic renders.",
    },
    {
        "path": "docs/reports/P11.5-006-side-by-side-comparison.md",
        "classes": [MIXED, HARDCODED],
        "affected_metrics": [
            "V1 vs V2 comparison",
            "'227.80 End-to-End FPS'",
            "production readiness",
        ],
        "evidence": [],
        "note": "Mixes real URFD results with synthetic UP-Fall and literal runtime values.",
    },
    {
        "path": "docs/reports/P11.5-004-candidate-freeze-report.md",
        "classes": [SYNTHETIC],
        "affected_metrics": ["'Pipeline Throughput 227.80 FPS'"],
        "evidence": [
            _ev("docs/reports/P11.5-004-candidate-freeze-report.md", 28, "**227.80 FPS**"),
        ],
        "note": (
            "Throughput timed on a synthetic black frame; this value was later copied as a "
            "literal into the P11.6 holdout runner and backbone study."
        ),
    },
    {
        "path": "docs/reports/P11.5-003-development-calibration-report.md",
        "classes": [MIXED],
        "affected_metrics": ["V2 dev calibration conclusions"],
        "evidence": [],
        "note": "Rendered from P11.5-003 JSON (real URFD + synthetic UP-Fall, contour fallback).",
    },
    {
        "path": "docs/reports/P11.5-005-final-metrics-report.md",
        "classes": [MIXED],
        "affected_metrics": ["V2 final metrics narrative"],
        "evidence": [],
        "note": "URFD real; UP-Fall synthetic renders.",
    },
    {
        "path": "docs/reports/P11.5-001-baseline-snapshot.json",
        "classes": [MIXED],
        "affected_metrics": ["V1 baseline snapshot incl. FA/h"],
        "evidence": [],
        "note": "Snapshots V1 results over real URFD and synthetic UP-Fall.",
    },
    {
        "path": "docs/reports/P11-006-error-limitations-analysis.md",
        "classes": [MIXED],
        "affected_metrics": ["error taxonomy", "'20/20 UAT proves system resilience'"],
        "evidence": [],
        "note": (
            "URFD error analysis is on real video (and burns URFD test for selection); UP-Fall "
            "findings are on synthetic renders; the resilience claim relies on synthetic UAT."
        ),
    },
    {
        "path": "docs/reports/P11-002-urfd-evaluation-report.md",
        "classes": [REAL, HARDCODED],
        "affected_metrics": ["URFD V1 narrative", "'Decode Failures 0/28'"],
        "evidence": [
            _ev(
                "docs/reports/P11-002-urfd-evaluation-report.md",
                76,
                "- **Decode Failures:** 0 / 28 sequences.",
            ),
        ],
        "note": (
            "Numbers derive from the real raw evaluation JSON, but the decode-failure line and "
            "robustness wording are template literals; cite the raw JSON instead."
        ),
    },
    # ---- Real measurements (kept as evidence, with limitations) -------------------------
    {
        "path": "docs/reports/P11-002-urfd-raw-evaluation.json",
        "classes": [REAL],
        "affected_metrics": ["URFD V1 TP1/FP10/TN6/FN11, P 9.09%, R 8.33%"],
        "evidence": [
            _ev(
                "scripts/dataset/evaluate_urfd_frozen.py",
                122,
                "cap = cv2.VideoCapture(str(vid_path))",
            ),
            _ev(
                "scripts/dataset/evaluate_urfd_frozen.py",
                468,
                "- **Decode Failures:** 0 / 28 sequences.",
            ),
        ],
        "note": (
            "Real URFD video -> TRT pose -> ByteTrack. Limitation: the report's 'Decode Failures "
            "0/28' line is a template literal. URFD test was error-analysed in P11-006, so it is "
            "burned for model selection."
        ),
    },
    {
        "path": "docs/reports/P11.5-005-urfd-raw-evaluation.json",
        "classes": [REAL],
        "affected_metrics": ["URFD V2 TP2/FP9/TN7/FN10, P 18.18%, R 16.67%"],
        "evidence": [
            _ev(
                "scripts/dataset/re_evaluate_v2_frozen.py",
                69,
                "cap = cv2.VideoCapture(str(video_path))",
            ),
            _ev("scripts/dataset/re_evaluate_v2_frozen.py", 86, "person = pose_frame.persons[0]"),
        ],
        "note": "Real URFD video. Limitation: only the first detected person is kept as track 1.",
    },
    {
        "path": "benchmarks/results/p9_004_tensorrt_fp16.json",
        "classes": [REAL],
        "affected_metrics": ["TRT FP16 212.91 FPS, p95 4.351 ms"],
        "evidence": [
            _ev(
                "src/eldercare/benchmark/harness.py",
                193,
                "rng.integers(0, 256, size=(config.frame_height, config.frame_width, 3)",
            )
        ],
        "note": (
            "Real GPU measurement, but on random-noise frames, batch 1, single stream, placeholder "
            "tracker, no classifier/decode/publish. Not an end-to-end or per-stream SLA."
        ),
    },
]


def normalised_sha256(path: Path) -> str:
    """sha256 over bytes with CRLF normalised to LF (checkout-independent)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def verify_evidence(ev: dict[str, Any]) -> None:
    lines = (ROOT / ev["file"]).read_text(encoding="utf-8").splitlines()
    line_text = lines[ev["line"] - 1] if 0 < ev["line"] <= len(lines) else ""
    if ev["pattern"] not in line_text:
        raise ValueError(f"Evidence mismatch: {ev['file']}:{ev['line']} lacks {ev['pattern']!r}")


def build_index() -> dict[str, Any]:
    artifact_paths = {a["path"] for a in ARTIFACTS}
    entries: list[dict[str, Any]] = []
    for art in ARTIFACTS:
        path = ROOT / art["path"]
        if not path.is_file():
            raise FileNotFoundError(art["path"])
        for cls in art["classes"]:
            if cls not in PROVENANCE_CLASSES:
                raise ValueError(f"Unknown provenance class {cls}")
        for ev in art["evidence"]:
            verify_evidence(ev)
        entries.append(
            {
                "path": art["path"],
                "sha256_lf": normalised_sha256(path),
                "provenance_classes": art["classes"],
                "deployment_evidence": art["classes"] == [REAL],
                "affected_metrics": art["affected_metrics"],
                "evidence": art["evidence"],
                "note": art["note"],
            }
        )

    # Evidence files that are not themselves indexed artifacts are hash-locked here so the
    # line citations stay verifiable even if those files later change.
    evidence_files = sorted(
        {ev["file"] for a in ARTIFACTS for ev in a["evidence"]} - artifact_paths
    )
    evidence_locks = {f: normalised_sha256(ROOT / f) for f in evidence_files}

    return {
        "schema_version": "1.0.0",
        "task_id": "P11.7-001",
        "title": "Evidence quarantine index — Phase 11 / 11.5 / 11.6 metric provenance",
        "hash_method": "sha256 over file bytes with CRLF normalised to LF",
        "provenance_classes": {
            REAL: "Measured from real inputs through the real pipeline (limitations noted).",
            SYNTHETIC: "Produced from generated/simulated inputs, not recorded footage.",
            HARDCODED: "Value typed into code or a template and presented as measured.",
            LABEL_DERIVED: "Model input generated from the ground-truth label (circular).",
            MIXED: "Combines real and synthetic sources in one figure or report.",
        },
        "policy": (
            "Only entries with deployment_evidence=true may be cited as measured performance. "
            "All other entries are retained byte-identical as historical records and must be "
            "labelled 'synthetic/unverified' wherever referenced."
        ),
        "artifact_count": len(entries),
        "artifacts": entries,
        "evidence_file_locks": evidence_locks,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    index = build_index()
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    real = sum(1 for e in index["artifacts"] if e["deployment_evidence"])
    logger.info(
        "Indexed %d artifacts (%d real-measured) -> %s", index["artifact_count"], real, INDEX_PATH
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
