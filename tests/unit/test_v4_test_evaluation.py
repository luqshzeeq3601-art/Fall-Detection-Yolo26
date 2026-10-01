# ruff: noqa: E501
"""Unit tests for V4 Held-Out Test Split Evaluation (P11.7-016)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.dataset.evaluate_v4_test_split import verify_freeze_manifest


def test_verify_freeze_manifest():
    """Verify cryptographic validation of all 9 frozen artifacts."""
    manifest = verify_freeze_manifest()
    assert manifest["status"] == "FROZEN_FOR_TEST_EVALUATION"
    assert len(manifest["artifacts"]) >= 9


def test_v4_test_evaluation_artifact_integrity():
    """Verify generated test evaluation JSON matches schema and provenance standards."""
    path = Path("docs/reports/P11.7-016-v4-test-evaluation.json")
    assert path.is_file(), f"Evaluation report not found at {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["task"] == "P11.7-016"
    assert "metrics" in data
    assert "summary_counts" in data
    assert "per_sequence_ledger" in data

    counts = data["summary_counts"]
    assert counts["total_sequences"] == 28
    assert counts["fall_sequences"] == 12
    assert counts["adl_sequences"] == 16

    metrics = data["metrics"]
    assert metrics["deployment_evidence"] is True
    assert metrics["provenance"] == "real_measured"
    assert metrics["actual_decoded_frames"] == 4600
    assert metrics["actual_processed_seconds"] > 150.0
    assert metrics["median_tta_sec"] <= 1.0
