"""Versioned prompt templates and builder functions for Agent/VLM enrichment (P10-004)."""

from __future__ import annotations

from typing import Any

DEFAULT_PROMPT_VERSION = "v1.0.0"

_PROMPT_TEMPLATES: dict[str, str] = {
    "v1.0.0": """You are an automated visual safety assistant for elder care environments.
Your role is to provide objective, non-diagnostic observational context for an alert.

SAFETY INSTRUCTIONS:
- Do not make clinical diagnoses (e.g., do not diagnose fractures, strokes, or trauma).
- Describe strictly what is visually observable in terms of posture, orientation, surroundings.
- If visual clarity is low or occlusion occurs, explicitly list uncertainty factors.

INCIDENT CONTEXT:
- Camera ID: {camera_id}
- Incident ID: {incident_id}
- Initial Fall Score: {fall_score}
- Detection Timestamp: {timestamp}

REQUIRED RESPONSE FORMAT:
Respond with a strict JSON object containing the following keys:
{{
  "schema_version": "1.0.0",
  "posture_description": "<detailed description of subject's posture and orientation>",
  "apparent_motion_context": "<visible trajectory or motion prior to rest, or null>",
  "environmental_context": "<description of room type, flooring, furniture, or obstacles>",
  "scene_summary": "<concise summary of the scene for the caregiver>",
  "confidence_assessment": "<high | medium | low | uncertain>",
  "uncertainty_factors": ["<list of any visual occlusions or ambiguous elements>"],
  "postural_state": "<lying_floor | sitting_floor | slumped_furniture | kneeling_floor | upright>",
  "potential_hazards": ["<list of nearby hazards such as spills, sharp edges, clutter>"]
}}
"""
}


def list_supported_prompt_versions() -> list[str]:
    """Return a list of all registered prompt template versions."""
    return list(_PROMPT_TEMPLATES.keys())


def build_enrichment_prompt(
    context: dict[str, Any] | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> str:
    """Render a structured enrichment prompt for the requested template version.

    Args:
        context: Dictionary containing incident metadata (camera_id, incident_id, etc.).
        prompt_version: Registered prompt template version tag.

    Returns:
        Rendered string prompt formatted for the VLM provider.

    Raises:
        ValueError: If the requested prompt_version is not supported.
    """
    template = _PROMPT_TEMPLATES.get(prompt_version)
    if template is None:
        supported = ", ".join(list_supported_prompt_versions())
        raise ValueError(
            f"Unsupported prompt version '{prompt_version}'. Supported versions: {supported}"
        )

    ctx = context or {}
    camera_id = ctx.get("camera_id", "unknown")
    incident_id = ctx.get("incident_id", "unknown")
    fall_score = f"{ctx.get('fall_score', 0.0):.2f}" if "fall_score" in ctx else "N/A"
    timestamp = ctx.get("timestamp", "unknown")

    return template.format(
        camera_id=camera_id,
        incident_id=incident_id,
        fall_score=fall_score,
        timestamp=timestamp,
    )
