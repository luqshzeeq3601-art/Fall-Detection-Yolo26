# ruff: noqa: E501
"""Unit tests for Phase 11.7 Final Gate & Metrics Consolidation (P11.7-018)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_final_metrics_consolidation_artifact_validity():
    """Verify final metrics consolidation JSON exists and matches required structure."""
    path = Path("docs/reports/P11.7-018-final-metrics-consolidation.json")
    if not path.is_file():
        path = Path("eldercare-vision/docs/reports/P11.7-018-final-metrics-consolidation.json")

    assert path.is_file(), f"Consolidation JSON missing at {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phase"] == "11.7"
    assert data["task"] == "P11.7-018"
    assert data["status"] == "APPROVED"
    assert "hardware_platform" in data
    assert "dataset_manifest" in data
    assert "benchmark_progression" in data
    assert "edge_inference_performance" in data
    assert "failure_mode_taxonomy" in data
    assert "governance_and_integrity" in data

    # Verify edge throughput > 30 FPS target
    assert data["edge_inference_performance"]["full_system_projected_fps"] >= 30.0
    assert data["edge_inference_performance"]["realtime_headroom_multiplier"] >= 2.0


def test_phase_gate_review_report_exists():
    """Verify Phase 11.7 gate review report markdown exists."""
    path = Path("docs/reports/P11.7-018-phase-gate-review.md")
    if not path.is_file():
        path = Path("eldercare-vision/docs/reports/P11.7-018-phase-gate-review.md")

    assert path.is_file(), f"Phase gate review markdown missing at {path}"
    content = path.read_text(encoding="utf-8")
    assert "PASS / APPROVED" in content
    assert "P11.7-001" in content
    assert "P11.7-018" in content
