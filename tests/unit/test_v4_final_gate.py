"""Unit tests for Phase Deployment Gate Verification & Target Enforcement (P11.8-002).

Enforces real accuracy, false alert rate, latency, and throughput gate checking
using check_deployment_gates_v4 and targets defined in config/phase_gate_targets.yaml.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from eldercare.fall_engine.evaluation.metrics_v4 import (
    DeploymentMetricsV4,
    check_deployment_gates_v4,
)

ROOT = Path(__file__).resolve().parents[2]
TARGETS_PATH = ROOT / "config" / "phase_gate_targets.yaml"
P11_7_016_JSON = ROOT / "docs" / "reports" / "P11.7-016-v4-test-evaluation.json"


def load_gate_targets() -> dict[str, Any]:
    """Load deployment gate targets from YAML configuration."""
    assert TARGETS_PATH.is_file(), f"Targets config missing at {TARGETS_PATH}"
    config = yaml.safe_load(TARGETS_PATH.read_text(encoding="utf-8"))
    return config["deployment_gates"]


def test_phase_gate_targets_config_valid():
    """Verify phase_gate_targets.yaml contains required target thresholds."""
    targets = load_gate_targets()
    assert targets["recall"] >= 0.95
    assert targets["precision"] >= 0.95
    assert targets["f1_score"] >= 0.95
    assert targets["long_form_false_alerts_per_camera_hour"] <= 1.0
    assert targets["p95_tta_sec"] <= 2.5
    assert targets["throughput_fps"] >= 15.0


def test_p11_7_016_evaluation_fails_deployment_gate():
    """Regression test: P11.7-016 evaluation JSON MUST fail the real deployment gate."""
    assert P11_7_016_JSON.is_file(), f"Evaluation JSON missing at {P11_7_016_JSON}"
    eval_data = json.loads(P11_7_016_JSON.read_text(encoding="utf-8"))
    metrics_dict = eval_data["metrics"]

    # Construct DeploymentMetricsV4 from P11.7-016 evaluation output
    metrics = DeploymentMetricsV4(
        tp=metrics_dict["tp"],
        fp=metrics_dict["fp"],
        tn=metrics_dict["tn"],
        fn=metrics_dict["fn"],
        total_sequences=metrics_dict["total_sequences"],
        precision=metrics_dict["precision"],
        recall=metrics_dict["recall"],
        f1_score=metrics_dict["f1_score"],
        f2_score=metrics_dict["f2_score"],
        accuracy=metrics_dict["accuracy"],
        missed_fall_rate=metrics_dict["missed_fall_rate"],
        short_clip_adl_fp_count=metrics_dict["short_clip_adl_fp_count"],
        short_clip_adl_total_count=metrics_dict["short_clip_adl_total_count"],
        short_clip_adl_fp_rate=metrics_dict["short_clip_adl_fp_rate"],
        long_form_false_alert_count=metrics_dict["long_form_false_alert_count"],
        long_form_processed_camera_hours=metrics_dict["long_form_processed_camera_hours"],
        long_form_false_alerts_per_camera_hour=metrics_dict[
            "long_form_false_alerts_per_camera_hour"
        ],
        long_form_fa_poisson_ci=tuple(metrics_dict["long_form_fa_poisson_ci"]),  # type: ignore[arg-type]
        actual_processed_seconds=metrics_dict["actual_processed_seconds"],
        actual_decoded_frames=metrics_dict["actual_decoded_frames"],
        median_tta_sec=metrics_dict["median_tta_sec"],
        p90_tta_sec=metrics_dict["p90_tta_sec"],
        p95_tta_sec=metrics_dict["p95_tta_sec"],
        tta_samples=metrics_dict["tta_samples"],
        duplicate_alert_rate=metrics_dict["duplicate_alert_rate"],
        usable_pose_rate=metrics_dict["usable_pose_rate"],
        track_continuity_rate=metrics_dict["track_continuity_rate"],
        id_switch_rate=metrics_dict["id_switch_rate"],
        throughput_fps=metrics_dict["throughput_fps"],
        p50_latency_ms=metrics_dict["p50_latency_ms"],
        p95_latency_ms=metrics_dict["p95_latency_ms"],
        e2e_alert_latency_sec=metrics_dict["e2e_alert_latency_sec"],
        hardware_metrics=metrics_dict.get("hardware_metrics", {}),
        subgroup_metrics=metrics_dict.get("subgroup_metrics", {}),
        provenance=metrics_dict.get("provenance", "real_measured"),
        deployment_evidence=metrics_dict.get("deployment_evidence", True),
        source_file_hashes=metrics_dict.get("source_file_hashes", {}),
        input_manifest_hash=metrics_dict.get("input_manifest_hash", ""),
        evaluated_at_utc=metrics_dict.get("evaluated_at_utc", ""),
        notes=metrics_dict.get("notes", ""),
    )

    targets = load_gate_targets()
    report = check_deployment_gates_v4(metrics, targets)

    # The gate must fail
    assert report["all_passed"] is False, "P11.7-016 metrics should NOT pass the deployment gate"
    failed_names = [item["metric"] for item in report["not_met"]]

    # Specifically recall, precision, and f1 must fail
    assert "recall" in failed_names, f"Expected recall to fail gate, got {metrics.recall}"
    assert "precision" in failed_names, f"Expected precision to fail gate, got {metrics.precision}"
    assert "f1_score" in failed_names, f"Expected f1_score to fail gate, got {metrics.f1_score}"


def test_deployment_gate_passes_on_compliant_v5_metrics():
    """Verify that check_deployment_gates_v4 approves compliant 95/95 metrics."""
    targets = load_gate_targets()
    compliant_metrics = DeploymentMetricsV4(
        tp=95,
        fp=5,
        tn=95,
        fn=5,
        total_sequences=200,
        precision=0.95,
        recall=0.95,
        f1_score=0.95,
        f2_score=0.95,
        accuracy=0.95,
        missed_fall_rate=0.05,
        short_clip_adl_fp_count=5,
        short_clip_adl_total_count=100,
        short_clip_adl_fp_rate=0.05,
        long_form_false_alert_count=10,
        long_form_processed_camera_hours=25.0,
        long_form_false_alerts_per_camera_hour=0.4,
        long_form_fa_poisson_ci=(0.19, 0.73),
        actual_processed_seconds=90000.0,
        actual_decoded_frames=2700000,
        median_tta_sec=1.1,
        p90_tta_sec=1.8,
        p95_tta_sec=2.1,
        tta_samples=95,
        duplicate_alert_rate=0.01,
        usable_pose_rate=0.95,
        track_continuity_rate=0.98,
        id_switch_rate=0.01,
        throughput_fps=22.5,
        p50_latency_ms=4.0,
        p95_latency_ms=8.0,
        e2e_alert_latency_sec=1.2,
        hardware_metrics={"gpu": "RTX 3070"},
        subgroup_metrics={},
        provenance="real_measured",
        deployment_evidence=True,
        source_file_hashes={},
        input_manifest_hash="test-hash",
        evaluated_at_utc="2026-09-25T00:00:00Z",
        notes="Compliant test metrics",
    )

    report = check_deployment_gates_v4(compliant_metrics, targets)
    assert report["all_passed"] is True, f"Compliant metrics failed gate: {report['not_met']}"
    assert len(report["not_met"]) == 0
