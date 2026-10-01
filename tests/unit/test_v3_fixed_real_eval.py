"""P11.7-005: Tests for V3-fixed real decoded-video evaluation baseline."""

from __future__ import annotations

import json
from pathlib import Path

from eldercare.fall_engine.evaluation.guardrails import MetricIntegrityGuard
from tests.local_artifacts import requires_local

ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = ROOT / "docs" / "reports" / "P11.7-005-v3-fixed-real-evaluation.json"
REPORT_MD = ROOT / "docs" / "reports" / "P11.7-005-v3-fixed-real-report.md"


def test_v3_fixed_real_report_exists_and_valid() -> None:
    """Ensure P11.7-005 report files exist and have valid structure."""
    assert REPORT_JSON.is_file(), f"Missing {REPORT_JSON}"
    assert REPORT_MD.is_file(), f"Missing {REPORT_MD}"

    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert data["task_id"] == "P11.7-005"
    assert "metrics" in data
    assert "per_sequence_results" in data


@requires_local("yolo26s-pose.engine")
def test_v3_fixed_real_integrity_guardrails() -> None:
    """Ensure V3-fixed evaluation output satisfies all metric integrity guardrails."""
    guard = MetricIntegrityGuard()
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    metrics = data["metrics"]

    assert metrics["provenance"] == "real_measured"
    assert metrics["deployment_evidence"] is True

    violations = guard.validate_metrics_dict(metrics)
    assert not violations, f"Integrity violations found: {violations}"


def test_v3_fixed_real_counts_and_metrics() -> None:
    """Verify measured counts, frame totals, and improved recall/precision from wiring fixes."""
    data = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    metrics = data["metrics"]
    results = data["per_sequence_results"]

    assert len(results) == 28
    assert metrics["total_sequences"] == 28
    assert metrics["tp"] == 6
    assert metrics["fp"] == 11
    assert metrics["tn"] == 5
    assert metrics["fn"] == 6

    # Verify metric improvement over V3-as-is (Recall 50.0% vs 33.3%, Precision 35.3% vs 26.7%)
    assert metrics["recall"] == 0.5000
    assert metrics["precision"] == 0.3529
    assert metrics["f1_score"] == 0.4138
    assert metrics["f2_score"] == 0.4615

    # Frames decoded must be exactly 4,600 across 28 clips
    assert metrics["actual_decoded_frames"] == 4600
    assert metrics["actual_processed_seconds"] == 153.33
    assert metrics["long_form_processed_camera_hours"] == 0.0
