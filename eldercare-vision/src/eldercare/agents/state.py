"""Lifecycle state definitions and job models for asynchronous Agent/VLM enrichment (P10-001)."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class EnrichmentStatus(str, enum.Enum):
    """Lifecycle states of an asynchronous incident enrichment job."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"


ALLOWED_ENRICHMENT_STATUSES = {s.value for s in EnrichmentStatus}


@dataclass
class EnrichmentJob:
    """Encapsulates execution context and state for an asynchronous enrichment job."""

    incident_id: str
    camera_id: str
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: EnrichmentStatus = EnrichmentStatus.PENDING
    created_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    retry_count: int = 0
    output: dict[str, Any] | None = None

    def mark_in_progress(self) -> None:
        """Transition job state to in-progress."""
        if self.status != EnrichmentStatus.PENDING:
            raise ValueError(f"Cannot transition to in_progress from status {self.status.value}")
        self.status = EnrichmentStatus.IN_PROGRESS
        self.started_at = _utc_now()

    def mark_completed(self, output: dict[str, Any], duration_ms: int | None = None) -> None:
        """Transition job state to completed."""
        if self.status != EnrichmentStatus.IN_PROGRESS:
            raise ValueError(f"Cannot transition to completed from status {self.status.value}")
        now = _utc_now()
        self.status = EnrichmentStatus.COMPLETED
        self.completed_at = now
        self.output = output
        if duration_ms is not None:
            self.duration_ms = duration_ms
        elif self.started_at is not None:
            self.duration_ms = max(0, int((now - self.started_at).total_seconds() * 1000.0))

    def mark_failed(
        self,
        error_code: str = "PROCESSING_ERROR",
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Transition job state to failed."""
        now = _utc_now()
        self.status = EnrichmentStatus.FAILED
        self.completed_at = now
        self.error_code = error_code
        self.error_message = error_message
        if duration_ms is not None:
            self.duration_ms = duration_ms
        elif self.started_at is not None:
            self.duration_ms = max(0, int((now - self.started_at).total_seconds() * 1000.0))

    def mark_timed_out(self, error_message: str | None = None) -> None:
        """Transition job state to timed_out."""
        now = _utc_now()
        self.status = EnrichmentStatus.TIMED_OUT
        self.completed_at = now
        self.error_code = "TIMEOUT"
        self.error_message = error_message or "Enrichment operation timed out"
        if self.started_at is not None:
            self.duration_ms = max(0, int((now - self.started_at).total_seconds() * 1000.0))

    def mark_skipped(self, reason: str = "SKIPPED_BY_RULE") -> None:
        """Transition job state to skipped."""
        now = _utc_now()
        self.status = EnrichmentStatus.SKIPPED
        self.completed_at = now
        self.error_code = reason
        self.duration_ms = 0
