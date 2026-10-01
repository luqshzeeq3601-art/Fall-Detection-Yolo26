"""P11.7-003: Tests for V3-as-is real decoded-video evaluation baseline."""

from __future__ import annotations

import json
from pathlib import Path

from eldercare.fall_engine.evaluation.guardrails import MetricIntegrityGuard
from tests.local_artifacts import requires_local

ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "docs" / "reports" / "P11.7-003-v3-asis-real-evaluation.json"
REPORT_MD = ROOT / "docs" / "reports" / "P11.7-003-v3-asis-real-report.md"


def test_v3_asis_real_report_exists_and_valid() -> None:
    """Ensure P11.7-003 report files exist and have valid structure."""
    assert REPORT_JSON.is_file(), f"Missing {REPORT_JSON}"
    assert REPORT_MD.is_file(), f"Missing {REPORT_MD}"

    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert data["task_id"] == "P11.7-003"
    assert "metrics" in data
    assert "per_sequence_results" in data


@requires_local("yolo26s-pose.engine")
def test_v3_asis_real_integrity_guardrails() -> None:
    """Ensure V3-as-is evaluation output satisfies all metric integrity guardrails."""
    guard = MetricIntegrityGuard()
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    metrics = data["metrics"]

    assert metrics["provenance"] == "real_measured"
    assert metrics["deployment_evidence"] is True

    violations = guard.validate_metrics_dict(metrics)
    assert not violations, f"Integrity violations found: {violations}"


def test_v3_asis_real_counts_and_separation() -> None:
    """Verify measured counts, frame totals, and separation of short-clip vs long-form."""
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    metrics = data["metrics"]
    results = data["per_sequence_results"]

    assert len(results) == 28
    assert metrics["total_sequences"] == 28
    assert metrics["tp"] == 4
    assert metrics["fp"] == 11
    assert metrics["tn"] == 5
    assert metrics["fn"] == 8

    # Accuracy, Recall, Precision checks
    assert abs(metrics["recall"] - (4.0 / 12.0)) < 0.001
    assert abs(metrics["precision"] - (4.0 / 15.0)) < 0.001
    assert abs(metrics["short_clip_adl_fp_rate"] - (11.0 / 16.0)) < 0.001

    # Frames decoded must be positive and backed by video
    assert metrics["actual_decoded_frames"] > 4000
    assert metrics["actual_processed_seconds"] > 100.0

    # Long-form hours is 0 because all URFD items are short clips
    assert metrics["long_form_processed_camera_hours"] == 0.0
