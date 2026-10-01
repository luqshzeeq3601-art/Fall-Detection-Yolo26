"""FastAPI router for Incident queries, details, and evidence streaming (P5-005)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from eldercare.api.dependencies import (
    get_evidence_storage,
    get_incident_repository,
    get_incident_service,
)
from eldercare.evidence.storage import EvidenceFileNotFoundError, EvidenceStorage
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import (
    EvidenceNotFoundError,
    IncidentDetailRead,
    IncidentFilter,
    IncidentNotFoundError,
    IncidentRead,
    IncidentReviewCreate,
    IncidentReviewRead,
    PaginatedIncidents,
)
from eldercare.incidents.service import IncidentService

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=PaginatedIncidents)
def list_incidents(
    camera_id: Annotated[str | None, Query(description="Filter by camera ID")] = None,
    status: Annotated[str | None, Query(description="Filter by detector state / status")] = None,
    review_label: Annotated[str | None, Query(description="Filter by human review label")] = None,
    needs_review: Annotated[
        bool,
        Query(description="Only unreviewed incidents the VLM flagged as uncertain or not a fall"),
    ] = False,
    from_time: Annotated[
        datetime | None, Query(alias="from", description="Filter by start time")
    ] = None,
    to_time: Annotated[datetime | None, Query(alias="to", description="Filter by end time")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Page limit")] = 50,
    offset: Annotated[int, Query(ge=0, description="Page offset")] = 0,
    cursor: Annotated[str | None, Query(description="Cursor token for pagination")] = None,
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)] = None,  # type: ignore[assignment]
) -> PaginatedIncidents:
    """List and filter detected incidents with pagination."""
    filter_params = IncidentFilter(
        camera_id=camera_id,
        status=status,
        review_label=review_label,
        needs_review=needs_review,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )
    items, total = repo.list_incidents(filter_params, load_relations=False)
    return PaginatedIncidents(
        items=[IncidentRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentDetailRead)
def get_incident_detail(
    incident_id: str,
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
) -> IncidentDetailRead:
    """Fetch complete incident detail with media evidence, reviews, and enrichments."""
    incident = repo.get_incident_by_id(incident_id, load_relations=True)
    if incident is None:
        raise IncidentNotFoundError(incident_id)
    return IncidentDetailRead.model_validate(incident)


@router.get("/{incident_id}/evidence/{evidence_id}")
def stream_incident_evidence(
    incident_id: str,
    evidence_id: str,
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
    storage: Annotated[EvidenceStorage, Depends(get_evidence_storage)],
) -> StreamingResponse:
    """Safely stream binary evidence for an incident with checksum verification headers."""
    incident = repo.get_incident_by_id(incident_id, load_relations=False)
    if incident is None:
        raise IncidentNotFoundError(incident_id)

    evidence = repo.get_evidence_by_id(incident_id=incident_id, evidence_id=evidence_id)
    if evidence is None:
        raise EvidenceNotFoundError(evidence_id, incident_id=incident_id)

    safe_path = storage.resolve_safe_path(evidence.storage_path)
    if not safe_path.is_file():
        raise EvidenceFileNotFoundError(evidence.storage_path)

    file_size = safe_path.stat().st_size
    headers = {
        "X-Evidence-SHA256": evidence.sha256,
        "Content-Length": str(file_size),
    }

    return StreamingResponse(
        storage.open_stream(evidence.storage_path),
        media_type=evidence.mime_type or "application/octet-stream",
        headers=headers,
    )


@router.post(
    "/{incident_id}/reviews",
    response_model=IncidentReviewRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_incident_review(
    incident_id: str,
    payload: IncidentReviewCreate,
    service: Annotated[IncidentService, Depends(get_incident_service)],
) -> IncidentReviewRead:
    """Submit an append-only human review decision for an incident.

    Guarantees that detector outputs (fall_score, model_name, evidence_features)
    remain completely unchanged.
    """
    review = service.submit_review(
        incident_id=incident_id,
        label=payload.label,
        notes=payload.notes,
        reviewer=payload.reviewer,
    )
    return IncidentReviewRead.model_validate(review)


@router.get(
    "/{incident_id}/reviews",
    response_model=list[IncidentReviewRead],
)
def list_incident_reviews(
    incident_id: str,
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
) -> list[IncidentReviewRead]:
    """List all appended reviews for an incident in chronological order."""
    incident = repo.get_incident_by_id(incident_id, load_relations=False)
    if incident is None:
        raise IncidentNotFoundError(incident_id)
    reviews = repo.list_reviews_for_incident(incident_id)
    return [IncidentReviewRead.model_validate(r) for r in reviews]
