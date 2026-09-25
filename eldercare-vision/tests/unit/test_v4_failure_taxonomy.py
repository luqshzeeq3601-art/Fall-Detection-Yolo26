# ruff: noqa: E501
"""Unit tests for Failure Mode Taxonomy & Error Analysis (P11.7-017)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analysis.analyze_v4_failure_modes import (
    FailureCategory,
    analyze_test_failures,
)


def test_failure_category_enum_completeness():
    """Verify all 4 standardized failure mode categories are defined."""
    assert len(FailureCategory) == 4
    categories = [cat.value for cat in FailureCategory]
    assert any("Occlusion" in cat for cat in categories)
    assert any("Kinetic Ambiguity" in cat for cat in categories)
    assert any("Progressive Slumps" in cat for cat in categories)
    assert any("Keypoint Jitter" in cat for cat in categories)


def test_failure_taxonomy_analysis_execution():
    """Verify error taxonomy analysis executes and produces structured JSON."""
    results = analyze_test_failures()
    assert results["phase"] == "11.7"
    assert results["task"] == "P11.7-017"
    assert results["total_test_sequences"] == 28
    assert results["total_errors"] == 17
    assert "error_breakdown" in results
    assert "category_distribution" in results
    assert "detailed_error_cases" in results
    assert len(results["detailed_error_cases"]) == 17
    assert len(results["deployment_hardening_recommendations"]) == 4


def test_failure_mode_artifact_json_exists():
    """Verify generated JSON report exists and is valid."""
    path = Path("docs/reports/P11.7-017-failure-mode-analysis.json")
    if not path.is_file():
        path = Path("eldercare-vision/docs/reports/P11.7-017-failure-mode-analysis.json")

    assert path.is_file(), f"Artifact not found at {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["task"] == "P11.7-017"
    assert data["error_breakdown"]["FP"] == 10
    assert data["error_breakdown"]["FN"] == 7
