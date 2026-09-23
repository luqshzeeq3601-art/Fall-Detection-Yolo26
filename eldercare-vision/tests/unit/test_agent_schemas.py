"""Unit tests for Agent/VLM prompt templates and strict output validation schemas (P10-004)."""

from __future__ import annotations

import json

import pytest

from eldercare.agents.client import ProviderMalformedResponseError
from eldercare.agents.prompts import (
    DEFAULT_PROMPT_VERSION,
    build_enrichment_prompt,
    list_supported_prompt_versions,
)
from eldercare.agents.schemas import (
    ConfidenceLevel,
    EnrichmentOutputSchema,
    PosturalState,
    parse_and_validate_enrichment_output,
)

# =====================================================================
# Prompt Templates & Builder Tests
# =====================================================================


def test_prompt_versions_catalog() -> None:
    versions = list_supported_prompt_versions()
    assert "v1.0.0" in versions
    assert DEFAULT_PROMPT_VERSION in versions


def test_build_enrichment_prompt_valid() -> None:
    context = {
        "camera_id": "cam-living-room",
        "incident_id": "inc-9921",
        "fall_score": 0.88,
        "timestamp": "2026-09-23T10:00:00Z",
    }
    prompt = build_enrichment_prompt(context=context, prompt_version="v1.0.0")
    assert "cam-living-room" in prompt
    assert "inc-9921" in prompt
    assert "0.88" in prompt
    assert "Do not make clinical diagnoses" in prompt
    assert "schema_version" in prompt


def test_build_enrichment_prompt_invalid_version() -> None:
    with pytest.raises(ValueError, match="Unsupported prompt version"):
        build_enrichment_prompt(context={}, prompt_version="v999.0.0")


# =====================================================================
# Output Schema Validation Tests
# =====================================================================


def test_valid_schema_instantiation() -> None:
    data = {
        "schema_version": "1.0.0",
        "posture_description": "Subject is horizontal on the floor adjacent to a coffee table",
        "apparent_motion_context": "Rapid descent detected prior to rest",
        "environmental_context": "Hardwood floor with scattered rug",
        "scene_summary": "Subject fell and remains on floor; immediate attention advised",
        "confidence_assessment": "high",
        "uncertainty_factors": [],
        "postural_state": "lying_floor",
        "potential_hazards": ["Corner of coffee table"],
    }
    schema = EnrichmentOutputSchema.model_validate(data)
    assert schema.schema_version == "1.0.0"
    assert schema.confidence_assessment == ConfidenceLevel.HIGH
    assert schema.postural_state == PosturalState.LYING_FLOOR
    assert len(schema.potential_hazards) == 1


def test_parse_and_validate_from_dict() -> None:
    payload = {
        "schema_version": "1.0.0",
        "posture_description": "Subject seated upright in armchair",
        "environmental_context": "Well-lit living room",
        "scene_summary": "Subject seated safely",
        "confidence_assessment": "medium",
    }
    result = parse_and_validate_enrichment_output(payload)
    assert isinstance(result, EnrichmentOutputSchema)
    assert result.scene_summary == "Subject seated safely"
    assert result.confidence_assessment == ConfidenceLevel.MEDIUM
    assert result.postural_state is None
    assert result.potential_hazards == []


def test_parse_and_validate_from_json_string() -> None:
    payload_str = json.dumps(
        {
            "schema_version": "1.0.0",
            "posture_description": "Person slumped over armchair armrest",
            "environmental_context": "Bedroom carpet near nightstand",
            "scene_summary": "Possible slump / loss of balance",
            "confidence_assessment": "uncertain",
            "uncertainty_factors": ["Partial occlusion from nightstand"],
            "postural_state": "slumped_furniture",
        }
    )
    result = parse_and_validate_enrichment_output(payload_str)
    assert result.postural_state == PosturalState.SLUMPED_FURNITURE
    assert len(result.uncertainty_factors) == 1


def test_reject_extra_field_injection() -> None:
    data = {
        "schema_version": "1.0.0",
        "posture_description": "Subject on floor",
        "environmental_context": "Living room",
        "scene_summary": "Subject on floor",
        "confidence_assessment": "high",
        "injected_extra_payload": "malicious_content",
    }
    with pytest.raises(ProviderMalformedResponseError, match="Extra inputs are not permitted"):
        parse_and_validate_enrichment_output(data)


def test_reject_missing_required_field() -> None:
    data = {
        "schema_version": "1.0.0",
        "posture_description": "Subject on floor",
        # Missing environmental_context & scene_summary
        "confidence_assessment": "high",
    }
    with pytest.raises(ProviderMalformedResponseError, match="validation error"):
        parse_and_validate_enrichment_output(data)


def test_reject_invalid_confidence_enum() -> None:
    data = {
        "schema_version": "1.0.0",
        "posture_description": "Subject on floor",
        "environmental_context": "Living room",
        "scene_summary": "Subject on floor",
        "confidence_assessment": "super_confident_invalid",
    }
    with pytest.raises(ProviderMalformedResponseError, match="validation error"):
        parse_and_validate_enrichment_output(data)


def test_reject_version_mismatch() -> None:
    data = {
        "schema_version": "2.0.0",
        "posture_description": "Subject on floor",
        "environmental_context": "Living room",
        "scene_summary": "Subject on floor",
        "confidence_assessment": "high",
    }
    with pytest.raises(ProviderMalformedResponseError, match="Schema version mismatch"):
        parse_and_validate_enrichment_output(data, expected_version="1.0.0")


def test_reject_invalid_json_string() -> None:
    with pytest.raises(ProviderMalformedResponseError, match="Failed to parse output JSON string"):
        parse_and_validate_enrichment_output("INVALID_JSON_NOT_AN_OBJECT")


def test_reject_invalid_payload_type() -> None:
    with pytest.raises(ProviderMalformedResponseError, match="Expected dictionary or JSON string"):
        parse_and_validate_enrichment_output(12345)  # type: ignore[arg-type]
