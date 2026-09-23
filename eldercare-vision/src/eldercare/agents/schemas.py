"""Strict output validation schemas and parsing utilities for Agent/VLM enrichment (P10-004)."""

from __future__ import annotations

import enum
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eldercare.agents.client import ProviderMalformedResponseError


class ConfidenceLevel(str, enum.Enum):
    """Subjective confidence assessment reported by the VLM."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class PosturalState(str, enum.Enum):
    """Observable postural category for the subject."""

    LYING_FLOOR = "lying_floor"
    SITTING_FLOOR = "sitting_floor"
    SLUMPED_FURNITURE = "slumped_furniture"
    KNEELING_FLOOR = "kneeling_floor"
    UPRIGHT = "upright"
    UNCLEAR = "unclear"


class EnrichmentOutputSchema(BaseModel):
    """Strict output schema validating structured Agent/VLM incident enrichment outputs."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: str = Field(
        default="1.0.0",
        description="Semantic version of the enrichment output schema",
    )
    posture_description: str = Field(
        ...,
        min_length=3,
        description="Detailed description of subject posture, joint positions, or orientation",
    )
    apparent_motion_context: str | None = Field(
        default=None,
        description="Observable trajectory or movement pattern prior to rest, if discernible",
    )
    environmental_context: str = Field(
        ...,
        min_length=3,
        description="Physical setting, room type, nearby furniture, or flooring characteristics",
    )
    scene_summary: str = Field(
        ...,
        min_length=3,
        description="Concise, non-clinical summary of the event for caregivers",
    )
    confidence_assessment: ConfidenceLevel = Field(
        ...,
        description="Confidence level regarding observational certainty",
    )
    uncertainty_factors: list[str] = Field(
        default_factory=list,
        description="Specific factors degrading visual clarity or interpretation",
    )
    postural_state: PosturalState | None = Field(
        default=None,
        description="Categorized posture category",
    )
    potential_hazards: list[str] = Field(
        default_factory=list,
        description="Surrounding environmental hazards (e.g. spills, sharp corners, clutter)",
    )


def parse_and_validate_enrichment_output(
    raw_output: dict[str, Any] | str,
    expected_version: str = "1.0.0",
) -> EnrichmentOutputSchema:
    """Parse and validate raw dictionary or JSON string output against EnrichmentOutputSchema.

    Args:
        raw_output: Raw JSON string or dictionary returned from VLM provider.
        expected_version: Expected schema semantic version.

    Returns:
        Validated EnrichmentOutputSchema instance.

    Raises:
        ProviderMalformedResponseError: If payload fails validation, has extra fields,
            or invalid types.
    """
    if isinstance(raw_output, str):
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise ProviderMalformedResponseError(
                message=f"Failed to parse output JSON string: {exc}",
                raw_error=exc,
            ) from exc
    elif isinstance(raw_output, dict):
        payload = raw_output
    else:
        raise ProviderMalformedResponseError(
            message=f"Expected dictionary or JSON string, got {type(raw_output).__name__}"
        )

    if not isinstance(payload, dict):
        raise ProviderMalformedResponseError(
            message=f"Decoded payload must be a JSON object, got {type(payload).__name__}"
        )

    # Version check if present
    version = payload.get("schema_version", expected_version)
    if version != expected_version:
        raise ProviderMalformedResponseError(
            message=f"Schema version mismatch: expected {expected_version}, got {version}"
        )

    try:
        return EnrichmentOutputSchema.model_validate(payload)
    except ValidationError as exc:
        raise ProviderMalformedResponseError(
            message=f"Enrichment output failed schema validation: {exc}",
            raw_error=exc,
        ) from exc
