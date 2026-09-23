"""Transactional service layer for incident lifecycle management (P5-002)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from eldercare.db.models import (
    AgentEnrichment,
    Incident,
    IncidentEvidence,
    IncidentReview,
)
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import (
    ALLOWED_REVIEW_LABELS,
    AgentEnrichmentCreate,
    IncidentCreate,
    IncidentEvidenceCreate,
    IncidentFilter,
    IncidentNotFoundError,
    IncidentReviewCreate,
    InvalidReviewLabelError,
)


class IncidentService:
    """Service managing business rules and transactional lifecycles for incidents."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record_fall_incident(
        self,
        camera_id: str,
        track_id: str,
        started_at: datetime,
        confirmed_at: datetime,
        fall_score: float,
        model_name: str,
        model_version: str,
        config_version: str,
        evidence_features: dict[str, Any],
        detector_state: str = "FALL_CONFIRMED",
        ended_at: datetime | None = None,
        auto_create_camera: bool = True,
        incident_id: str | None = None,
    ) -> Incident:
        """Validate and persist a newly detected fall incident.

        Optionally auto-provisions the Camera entity if auto_create_camera is True.
        """
        payload = IncidentCreate(
            id=incident_id,
            camera_id=camera_id,
            track_id=track_id,
            started_at=started_at,
            confirmed_at=confirmed_at,
            ended_at=ended_at,
            detector_state=detector_state,
            fall_score=fall_score,
            model_name=model_name,
            model_version=model_version,
            config_version=config_version,
            evidence_features=evidence_features,
        )

        with self._session_factory() as session:
            try:
                repo = IncidentRepository(session)
                if auto_create_camera:
                    repo.get_or_create_camera(camera_id=camera_id)

                incident = repo.create_incident(payload)
                session.commit()
                # Reload with relations before session closure so returned instance is populated
                return repo.get_incident_by_id(incident.id, load_relations=True)  # type: ignore[return-value]
            except Exception:
                session.rollback()
                raise

    def attach_evidence(
        self,
        incident_id: str,
        evidence_type: str,
        storage_path: str,
        mime_type: str,
        sha256: str,
        captured_at: datetime,
        evidence_id: str | None = None,
    ) -> IncidentEvidence:
        """Attach verified media evidence to an existing incident."""
        payload = IncidentEvidenceCreate(
            id=evidence_id,
            evidence_type=evidence_type,
            storage_path=storage_path,
            mime_type=mime_type,
            sha256=sha256,
            captured_at=captured_at,
        )

        with self._session_factory() as session:
            try:
                repo = IncidentRepository(session)
                evidence = repo.add_evidence(incident_id=incident_id, data=payload)
                session.commit()
                session.refresh(evidence)
                return evidence
            except Exception:
                session.rollback()
                raise

    def submit_review(
        self,
        incident_id: str,
        label: str,
        notes: str | None = None,
        reviewer: str | None = None,
        review_id: str | None = None,
    ) -> IncidentReview:
        """Submit a human review decision to the append-only ledger.

        Guarantees that detector outputs (fall_score, model_name, etc.) remain untouched.
        """
        if label not in ALLOWED_REVIEW_LABELS:
            raise InvalidReviewLabelError(label)

        payload = IncidentReviewCreate(
            id=review_id,
            label=label,
            notes=notes,
            reviewer=reviewer,
        )

        with self._session_factory() as session:
            try:
                repo = IncidentRepository(session)
                review = repo.add_review(
                    incident_id=incident_id,
                    label=payload.label,
                    notes=payload.notes,
                    reviewer=payload.reviewer,
                    review_id=payload.id,
                )
                session.commit()
                session.refresh(review)
                return review
            except Exception:
                session.rollback()
                raise

    def record_enrichment(
        self,
        incident_id: str,
        prompt_version: str,
        status: str = "pending",
        provider: str | None = None,
        model: str | None = None,
        output: dict[str, Any] | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
        completed_at: datetime | None = None,
        enrichment_id: str | None = None,
    ) -> AgentEnrichment:
        """Record an asynchronous Agent/VLM enrichment result."""
        payload = AgentEnrichmentCreate(
            id=enrichment_id,
            prompt_version=prompt_version,
            status=status,
            provider=provider,
            model=model,
            output=output,
            error_code=error_code,
            duration_ms=duration_ms,
            completed_at=completed_at,
        )

        with self._session_factory() as session:
            try:
                repo = IncidentRepository(session)
                enrichment = repo.add_enrichment(incident_id=incident_id, data=payload)
                session.commit()
                session.refresh(enrichment)
                return enrichment
            except Exception:
                session.rollback()
                raise

    def get_incident(self, incident_id: str, load_relations: bool = True) -> Incident:
        """Fetch incident by identifier or raise IncidentNotFoundError."""
        with self._session_factory() as session:
            repo = IncidentRepository(session)
            incident = repo.get_incident_by_id(incident_id, load_relations=load_relations)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            return incident

    def list_incidents(
        self, filter_params: IncidentFilter, load_relations: bool = False
    ) -> tuple[Sequence[Incident], int]:
        """Query and paginate incidents matching filter specifications."""
        with self._session_factory() as session:
            repo = IncidentRepository(session)
            return repo.list_incidents(filter_params, load_relations=load_relations)

    def update_incident_lifecycle(
        self,
        incident_id: str,
        ended_at: datetime | None = None,
        detector_state: str | None = None,
    ) -> Incident:
        """Update lifecycle state and ended timestamp of an incident."""
        with self._session_factory() as session:
            try:
                repo = IncidentRepository(session)
                incident = repo.update_incident_state(
                    incident_id=incident_id,
                    ended_at=ended_at,
                    detector_state=detector_state,
                )
                session.commit()
                return repo.get_incident_by_id(incident.id, load_relations=True)  # type: ignore[return-value]
            except Exception:
                session.rollback()
                raise
