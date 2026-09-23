"""Data access repository for Incidents, Evidence, Reviews, and Enrichments (P5-002)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from eldercare.db.models import (
    AgentEnrichment,
    Camera,
    Incident,
    IncidentEvidence,
    IncidentReview,
)
from eldercare.incidents.schemas import (
    AgentEnrichmentCreate,
    CameraNotFoundError,
    IncidentCreate,
    IncidentEvidenceCreate,
    IncidentFilter,
    IncidentNotFoundError,
)


class IncidentRepository:
    """Repository handling database operations for incidents and related entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Return the underlying active database session."""
        return self._session

    # ==========================================================================
    # Camera Operations
    # ==========================================================================

    def get_camera(self, camera_id: str) -> Camera | None:
        """Retrieve a camera by its unique identifier."""
        return self._session.scalar(select(Camera).where(Camera.id == camera_id))

    def get_or_create_camera(
        self, camera_id: str, name: str | None = None, status: str = "unknown"
    ) -> Camera:
        """Fetch an existing camera or create a new camera record if absent."""
        camera = self.get_camera(camera_id)
        if camera is None:
            camera = Camera(
                id=camera_id,
                name=name or f"Camera {camera_id}",
                status=status,
                enabled=True,
            )
            self._session.add(camera)
            self._session.flush()
        return camera

    # ==========================================================================
    # Incident CRUD & Filtering
    # ==========================================================================

    def create_incident(self, data: IncidentCreate) -> Incident:
        """Persist a new incident record.

        Raises:
            CameraNotFoundError: If the referenced camera_id does not exist in the database.
        """
        camera = self.get_camera(data.camera_id)
        if camera is None:
            raise CameraNotFoundError(data.camera_id)

        incident_id = data.id or str(uuid.uuid4())
        incident = Incident(
            id=incident_id,
            camera_id=data.camera_id,
            track_id=data.track_id,
            started_at=data.started_at,
            confirmed_at=data.confirmed_at,
            ended_at=data.ended_at,
            detector_state=data.detector_state,
            fall_score=data.fall_score,
            model_name=data.model_name,
            model_version=data.model_version,
            config_version=data.config_version,
            evidence_features=data.evidence_features,
        )
        self._session.add(incident)
        self._session.flush()
        return incident

    def get_incident_by_id(self, incident_id: str, load_relations: bool = True) -> Incident | None:
        """Retrieve an incident by primary key with optional eager relation loading."""
        stmt = select(Incident).where(Incident.id == incident_id)
        if load_relations:
            stmt = stmt.options(
                selectinload(Incident.evidence),
                selectinload(Incident.reviews),
                selectinload(Incident.enrichments),
            )
        return self._session.scalar(stmt)

    def list_incidents(
        self, filter_params: IncidentFilter, load_relations: bool = False
    ) -> tuple[Sequence[Incident], int]:
        """Query incidents with filtering, sorting, and pagination.

        Returns:
            Tuple of (list of matched Incident records, total count matching filter).
        """
        # Base query
        stmt = select(Incident)
        count_stmt = select(func.count(distinct(Incident.id)))

        # Filters
        if filter_params.camera_id:
            stmt = stmt.where(Incident.camera_id == filter_params.camera_id)
            count_stmt = count_stmt.where(Incident.camera_id == filter_params.camera_id)

        if filter_params.status:
            stmt = stmt.where(Incident.detector_state == filter_params.status)
            count_stmt = count_stmt.where(Incident.detector_state == filter_params.status)

        if filter_params.from_time:
            stmt = stmt.where(Incident.confirmed_at >= filter_params.from_time)
            count_stmt = count_stmt.where(Incident.confirmed_at >= filter_params.from_time)

        if filter_params.to_time:
            stmt = stmt.where(Incident.confirmed_at <= filter_params.to_time)
            count_stmt = count_stmt.where(Incident.confirmed_at <= filter_params.to_time)

        if filter_params.review_label:
            has_review = Incident.reviews.any(IncidentReview.label == filter_params.review_label)
            stmt = stmt.where(has_review)
            count_stmt = count_stmt.where(has_review)

        total_count = self._session.scalar(count_stmt) or 0

        # Eager relation loading if requested
        if load_relations:
            stmt = stmt.options(
                selectinload(Incident.evidence),
                selectinload(Incident.reviews),
                selectinload(Incident.enrichments),
            )

        # Ordering & Pagination
        stmt = stmt.order_by(Incident.confirmed_at.desc(), Incident.id.desc())
        stmt = stmt.offset(filter_params.offset).limit(filter_params.limit)

        results = self._session.scalars(stmt).all()
        return results, total_count

    def update_incident_state(
        self,
        incident_id: str,
        ended_at: datetime | None = None,
        detector_state: str | None = None,
    ) -> Incident:
        """Update mutable lifecycle fields of an incident.

        Core detection parameters (fall_score, model_name, evidence_features, etc.)
        are strictly immutable and cannot be modified here.
        """
        incident = self.get_incident_by_id(incident_id, load_relations=False)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

        if ended_at is not None:
            incident.ended_at = ended_at
        if detector_state is not None:
            incident.detector_state = detector_state

        self._session.flush()
        return incident

    # ==========================================================================
    # Evidence Operations
    # ==========================================================================

    def add_evidence(self, incident_id: str, data: IncidentEvidenceCreate) -> IncidentEvidence:
        """Attach media evidence to an existing incident."""
        incident = self.get_incident_by_id(incident_id, load_relations=False)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

        evidence_id = data.id or str(uuid.uuid4())
        evidence = IncidentEvidence(
            id=evidence_id,
            incident_id=incident_id,
            evidence_type=data.evidence_type,
            storage_path=data.storage_path,
            mime_type=data.mime_type,
            sha256=data.sha256,
            captured_at=data.captured_at,
        )
        self._session.add(evidence)
        self._session.flush()
        return evidence

    def get_evidence_by_id(self, incident_id: str, evidence_id: str) -> IncidentEvidence | None:
        """Fetch specific evidence record for an incident."""
        stmt = select(IncidentEvidence).where(
            IncidentEvidence.id == evidence_id,
            IncidentEvidence.incident_id == incident_id,
        )
        return self._session.scalar(stmt)

    def list_evidence_for_incident(self, incident_id: str) -> Sequence[IncidentEvidence]:
        """List all evidence attached to an incident ordered chronologically."""
        stmt = (
            select(IncidentEvidence)
            .where(IncidentEvidence.incident_id == incident_id)
            .order_by(IncidentEvidence.captured_at.asc())
        )
        return self._session.scalars(stmt).all()

    # ==========================================================================
    # Review Ledger (Append-Only)
    # ==========================================================================

    def add_review(
        self,
        incident_id: str,
        label: str,
        notes: str | None = None,
        reviewer: str | None = None,
        review_id: str | None = None,
    ) -> IncidentReview:
        """Append a human review decision to the incident's immutable ledger."""
        incident = self.get_incident_by_id(incident_id, load_relations=False)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

        rev_id = review_id or str(uuid.uuid4())
        review = IncidentReview(
            id=rev_id,
            incident_id=incident_id,
            label=label,
            notes=notes,
            reviewer=reviewer,
        )
        self._session.add(review)
        self._session.flush()
        return review

    def list_reviews_for_incident(self, incident_id: str) -> Sequence[IncidentReview]:
        """List all reviews for an incident in order of creation."""
        stmt = (
            select(IncidentReview)
            .where(IncidentReview.incident_id == incident_id)
            .order_by(IncidentReview.created_at.asc())
        )
        return self._session.scalars(stmt).all()

    # ==========================================================================
    # Agent / VLM Enrichment
    # ==========================================================================

    def add_enrichment(self, incident_id: str, data: AgentEnrichmentCreate) -> AgentEnrichment:
        """Create or record an asynchronous Agent/VLM enrichment entry."""
        incident = self.get_incident_by_id(incident_id, load_relations=False)
        if incident is None:
            raise IncidentNotFoundError(incident_id)

        enrichment_id = data.id or str(uuid.uuid4())
        enrichment = AgentEnrichment(
            id=enrichment_id,
            incident_id=incident_id,
            status=data.status,
            provider=data.provider,
            model=data.model,
            prompt_version=data.prompt_version,
            output=data.output,
            error_code=data.error_code,
            duration_ms=data.duration_ms,
            completed_at=data.completed_at,
        )
        self._session.add(enrichment)
        self._session.flush()
        return enrichment
