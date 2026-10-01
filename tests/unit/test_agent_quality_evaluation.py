"""Unit tests for Agent/VLM quality evaluation suite and rubric engine (P10-006)."""

from __future__ import annotations

import pytest

from eldercare.agents.client import MockVLMProvider
from eldercare.agents.evaluation import (
    STANDARD_BENCHMARK_SCENARIOS,
    AgentQualityEvaluator,
    ScenarioDefinition,
)
from eldercare.agents.schemas import ConfidenceLevel, PosturalState


@pytest.mark.asyncio
async def test_standard_benchmark_suite_all_pass() -> None:
    evaluator = AgentQualityEvaluator(prompt_version="v1.0.0")
    provider = MockVLMProvider()
    summary = await evaluator.evaluate_suite(
        provider=provider, scenarios=STANDARD_BENCHMARK_SCENARIOS
    )

    assert summary.total_scenarios == 4
    assert summary.passed_scenarios == 4
    assert summary.all_passed is True
    assert summary.mean_score_percentage == 100.0

    report_md = evaluator.render_markdown_report(summary)
    assert "# P10-006 — Agent/VLM Quality Evaluation Report" in report_md
    assert "SCEN-001" in report_md
    assert "SCEN-004" in report_md


@pytest.mark.asyncio
async def test_evaluator_catches_forbidden_diagnostic_term() -> None:
    evaluator = AgentQualityEvaluator()
    scenario = ScenarioDefinition(
        scenario_id="SCEN-TEST-DIAG",
        title="Diagnostic Violation Test",
        context={"camera_id": "c1", "incident_id": "i1"},
        ground_truth_posture=PosturalState.LYING_FLOOR,
        ground_truth_confidence=ConfidenceLevel.HIGH,
    )
    # Output containing forbidden clinical word "fracture"
    provider = MockVLMProvider(
        default_response={
            "schema_version": "1.0.0",
            "posture_description": "Subject on floor with suspected hip fracture",
            "environmental_context": "Living room floor",
            "scene_summary": "Subject suffered a severe fracture after falling",
            "confidence_assessment": "high",
            "uncertainty_factors": [],
            "postural_state": "lying_floor",
        }
    )
    result = await evaluator.evaluate_scenario(scenario, provider)
    assert result.non_diagnostic_safe is False
    assert result.passed is False
    assert any("Forbidden clinical diagnosis" in v for v in result.violations)


@pytest.mark.asyncio
async def test_evaluator_catches_posture_mismatch() -> None:
    evaluator = AgentQualityEvaluator()
    scenario = ScenarioDefinition(
        scenario_id="SCEN-TEST-POSTURE",
        title="Posture Mismatch Test",
        context={"camera_id": "c1", "incident_id": "i1"},
        ground_truth_posture=PosturalState.LYING_FLOOR,
        ground_truth_confidence=ConfidenceLevel.HIGH,
    )
    provider = MockVLMProvider(
        default_response={
            "schema_version": "1.0.0",
            "posture_description": "Subject standing upright near window",
            "environmental_context": "Living room floor",
            "scene_summary": "Subject standing normally",
            "confidence_assessment": "high",
            "uncertainty_factors": [],
            "postural_state": "upright",
        }
    )
    result = await evaluator.evaluate_scenario(scenario, provider)
    assert result.posture_matched is False
    assert result.passed is False


@pytest.mark.asyncio
async def test_evaluator_catches_uncalibrated_uncertainty_under_occlusion() -> None:
    evaluator = AgentQualityEvaluator()
    scenario = ScenarioDefinition(
        scenario_id="SCEN-TEST-UNCERT",
        title="Occlusion Uncertainty Test",
        context={"camera_id": "c1", "incident_id": "i1"},
        ground_truth_posture=PosturalState.LYING_FLOOR,
        ground_truth_confidence=ConfidenceLevel.UNCERTAIN,
        expect_uncertainty=True,
    )
    # Missing uncertainty factors despite expected occlusion
    provider = MockVLMProvider(
        default_response={
            "schema_version": "1.0.0",
            "posture_description": "Subject on floor",
            "environmental_context": "Bedroom",
            "scene_summary": "Subject on floor",
            "confidence_assessment": "high",
            "uncertainty_factors": [],  # Empty when uncertainty was expected
            "postural_state": "lying_floor",
        }
    )
    result = await evaluator.evaluate_scenario(scenario, provider)
    assert result.uncertainty_calibrated is False
    assert result.passed is False
