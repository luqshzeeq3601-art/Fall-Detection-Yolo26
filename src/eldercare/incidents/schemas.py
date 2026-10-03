"""Pydantic DTOs, request/response schemas, and domain exceptions for Incidents (P5-002)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewLabel(str, enum.Enum):
    """Allowed human review decisions."""

    CONFIRMED_FALL = "confirmed_fall"
    NON_FALL = "non_fall"
    UNCERTAIN = "uncertain"


ALLOWED_REVIEW_LABELS = {label.value for label in ReviewLabel}


class EvidenceType(str, enum.Enum):
    """Evidence media types."""

    SNAPSHOT = "snapshot"
    VIDEO_CLIP = "video_clip"


ALLOWED_EVIDENCE_TYPES = {t.value for t in EvidenceType}


# ==============================================================================
# Domain Exceptions
# ==============================================================================


class IncidentDomainError(Exception):
    """Base exception for incident domain logic."""


class IncidentNotFoundError(IncidentDomainError):
    """Raised when an incident ID does not exist."""

    def __init__(self, incident_id: str) -> None:
        super().__init__(f"Incident '{incident_id}' not found.")
        self.incident_id = incident_id


class CameraNotFoundError(IncidentDomainError):
    """Raised when a camera ID is referenced but does not exist."""

    def __init__(self, camera_id: str) -> None:
        super().__init__(f"Camera '{camera_id}' not found.")
        self.camera_id = camera_id


class InvalidReviewLabelError(IncidentDomainError):
    """Raised when an unrecognized review label is submitted."""

    def __init__(self, label: str) -> None:
        super().__init__(
            f"Invalid review label '{label}'. Allowed labels: {sorted(ALLOWED_REVIEW_LABELS)}"
        )
        self.label = label


class EvidenceNotFoundError(IncidentDomainError):
    """Raised when requested evidence does not exist."""

    def __init__(self, evidence_id: str, incident_id: str | None = None) -> None:
        msg = f"Evidence '{evidence_id}' not found"
        if incident_id:
            msg += f" for incident '{incident_id}'"
        super().__init__(msg + ".")
        self.evidence_id = evidence_id
        self.incident_id = incident_id


class ImmutableDetectorRecordError(IncidentDomainError):
    """Raised when an illegal attempt is made to mutate detector outputs."""


# ==============================================================================
# Creation / Mutation DTOs
# ==============================================================================


class IncidentCreate(BaseModel):
    """Payload for creating a new detected incident."""

    camera_id: str = Field(..., min_length=1, max_length=64)
    track_id: str = Field(..., min_length=1, max_length=64)
    started_at: datetime
    confirmed_at: datetime
    fall_score: float = Field(..., ge=0.0, le=1.0)
    model_name: str = Field(..., min_length=1, max_length=128)
    model_version: str = Field(..., min_length=1, max_length=128)
    config_version: str = Field(..., min_length=1, max_length=128)
    evidence_features: dict[str, Any] = Field(default_factory=dict)
    detector_state: str = Field(default="FALL_CONFIRMED", max_length=64)
    ended_at: datetime | None = None
    id: str | None = Field(default=None, max_length=36)

    model_config = ConfigDict(extra="forbid")


class IncidentEvidenceCreate(BaseModel):
    """Payload for registering media evidence."""

    evidence_type: str = Field(..., min_length=1, max_length=32)
    storage_path: str = Field(..., min_length=1, max_length=512)
    mime_type: str = Field(..., min_length=1, max_length=64)
    sha256: str = Field(..., min_length=64, max_length=64)
    captured_at: datetime
    id: str | None = Field(default=None, max_length=36)

    @field_validator("evidence_type")
    @classmethod
    def validate_evidence_type(cls, value: str) -> str:
        if value not in ALLOWED_EVIDENCE_TYPES:
            raise ValueError(
                f"Invalid evidence type '{value}'. Allowed: {sorted(ALLOWED_EVIDENCE_TYPES)}"
            )
        return value

    model_config = ConfigDict(extra="forbid")


class IncidentReviewCreate(BaseModel):
    """Payload for submitting an append-only human review."""

    label: str = Field(..., min_length=1, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=128)
    id: str | None = Field(default=None, max_length=36)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if value not in ALLOWED_REVIEW_LABELS:
            raise ValueError(
                f"Invalid review label '{value}'. Allowed: {sorted(ALLOWED_REVIEW_LABELS)}"
            )
        return value

    model_config = ConfigDict(extra="forbid")


class AgentEnrichmentCreate(BaseModel):
    """Payload for creating or updating an AI enrichment record."""

    prompt_version: str = Field(..., min_length=1, max_length=64)
    status: str = Field(default="pending", max_length=32)
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    output: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=64)
    duration_ms: int | None = Field(default=None, ge=0)
    completed_at: datetime | None = None
    id: str | None = Field(default=None, max_length=36)

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# Query / Filter DTO
# ==============================================================================


class IncidentFilter(BaseModel):
    """Filter and pagination parameters for listing incidents."""

    camera_id: str | None = None
    status: str | None = None
    review_label: str | None = None
    needs_review: bool = False
    q: str | None = Field(default=None, max_length=128)
    reviewed: bool | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    cursor: str | None = None

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# Read / Response DTOs
# ==============================================================================


class IncidentEvidenceRead(BaseModel):
    """Read schema for incident media evidence."""

    id: str
    incident_id: str
    evidence_type: str
    storage_path: str
    mime_type: str
    sha256: str
    captured_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentReviewRead(BaseModel):
    """Read schema for human review entry."""

    id: str
    incident_id: str
    label: str
    notes: str | None = None
    reviewer: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentEnrichmentRead(BaseModel):
    """Read schema for agent enrichment."""

    id: str
    incident_id: str
    status: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    output: dict[str, Any] | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class IncidentRead(BaseModel):
    """Standard read schema for incident summary."""

    id: str
    camera_id: str
    track_id: str
    started_at: datetime
    confirmed_at: datetime
    ended_at: datetime | None = None
    detector_state: str
    fall_score: float
    model_name: str
    model_version: str
    config_version: str
    evidence_features: dict[str, Any]
    created_at: datetime
    # Latest human review label (None = not reviewed yet); filled in by the API.
    review_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class IncidentDetailRead(IncidentRead):
    """Detailed read schema for an incident including all relations."""

    evidence: list[IncidentEvidenceRead] = Field(default_factory=list)
    reviews: list[IncidentReviewRead] = Field(default_factory=list)
    enrichments: list[AgentEnrichmentRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PaginatedIncidents(BaseModel):
    """Envelope for paginated list of incidents."""

    items: list[IncidentRead]
    total: int
    limit: int
    offset: int
