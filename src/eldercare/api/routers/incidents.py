"""FastAPI router for Incident queries, details, and evidence streaming (P5-005)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eldercare.api.dependencies import (
    get_current_user,
    get_db,
    get_evidence_storage,
    get_incident_repository,
    get_incident_service,
)
from eldercare.api.workspace import load_workspace_settings
from eldercare.db.models import Incident, IncidentReview, User
from eldercare.evidence.storage import EvidenceFileNotFoundError, EvidenceStorage
from eldercare.incidents.export import build_reviewed_dataset, to_jsonl
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
    reviewed: Annotated[
        bool | None, Query(description="Only incidents with (true) or without (false) a review")
    ] = None,
    q: Annotated[
        str | None,
        Query(max_length=128, description="Search incident ID, camera ID/name or track ID"),
    ] = None,
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
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> PaginatedIncidents:
    """List and filter detected incidents with pagination."""
    filter_params = IncidentFilter(
        camera_id=camera_id,
        status=status,
        review_label=review_label,
        needs_review=needs_review,
        q=q or None,
        reviewed=reviewed,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )
    items, total = repo.list_incidents(filter_params, load_relations=False)
    labels = _latest_review_labels(db, [item.id for item in items])
    return PaginatedIncidents(
        items=[
            IncidentRead.model_validate(item).model_copy(
                update={"review_label": labels.get(item.id)}
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _latest_review_labels(db: Session, incident_ids: list[str]) -> dict[str, str]:
    """Most recent review label per incident (append-only ledger, so the last wins)."""
    if not incident_ids:
        return {}
    labels: dict[str, str] = {}
    rows = db.execute(
        select(IncidentReview.incident_id, IncidentReview.label)
        .where(IncidentReview.incident_id.in_(incident_ids))
        .order_by(IncidentReview.created_at, IncidentReview.id)
    )
    for incident_id, label in rows:
        labels[incident_id] = label
    return labels


class DailyCount(BaseModel):
    date: str
    count: int


class IncidentStats(BaseModel):
    """Aggregate incident counts for the overview."""

    total: int
    today: int
    unreviewed: int
    reviewed: int
    confirmed_falls: int
    false_alarms: int
    last_7_days: list[DailyCount]


def _as_db_time(value: datetime, db: Session) -> datetime:
    value = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if db.get_bind().dialect.name == "sqlite":
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@router.get("/stats", response_model=IncidentStats)
def incident_stats(
    db: Annotated[Session, Depends(get_db)],
    day_start: Annotated[
        datetime | None,
        Query(description="Start of the caller's local day (ISO-8601 with offset)"),
    ] = None,
) -> IncidentStats:
    """Totals, today's count, review backlog and a 7-day daily series."""
    start = (
        _as_aware(day_start)
        if day_start
        else datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    window_start = start - timedelta(days=6)
    total = db.scalar(select(func.count(Incident.id))) or 0
    unreviewed = db.scalar(select(func.count(Incident.id)).where(~Incident.reviews.any())) or 0

    latest_label: dict[str, str] = {}
    for incident_id, label in db.execute(
        select(IncidentReview.incident_id, IncidentReview.label).order_by(
            IncidentReview.created_at, IncidentReview.id
        )
    ):
        latest_label[incident_id] = label

    recent = db.scalars(
        select(Incident.confirmed_at).where(Incident.confirmed_at >= _as_db_time(window_start, db))
    ).all()
    buckets = [0] * 7
    for confirmed in recent:
        index = int((_as_aware(confirmed) - window_start) // timedelta(days=1))
        if 0 <= index < 7:
            buckets[index] += 1
    return IncidentStats(
        total=total,
        today=buckets[6],
        unreviewed=unreviewed,
        reviewed=total - unreviewed,
        confirmed_falls=sum(1 for v in latest_label.values() if v == "confirmed_fall"),
        false_alarms=sum(1 for v in latest_label.values() if v == "non_fall"),
        last_7_days=[
            DailyCount(date=(window_start + timedelta(days=i)).date().isoformat(), count=c)
            for i, c in enumerate(buckets)
        ],
    )


@router.get("/export.jsonl")
def export_reviewed_dataset(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    include_uncertain: Annotated[bool | None, Query()] = None,
    ids: Annotated[list[str] | None, Query(description="Restrict to these incident IDs")] = None,
) -> Response:
    """Retraining manifest (JSON Lines) of human-reviewed incidents."""
    if include_uncertain is None:
        include_uncertain = load_workspace_settings(db).export_include_uncertain
    records = build_reviewed_dataset(
        request.app.state.session_factory, include_uncertain=include_uncertain
    )
    if ids:
        wanted = set(ids)
        records = [r for r in records if r.get("incident_id") in wanted]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=to_jsonl(records),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="eldercare-reviewed-{stamp}.jsonl"',
            "X-Record-Count": str(len(records)),
        },
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
    detail = IncidentDetailRead.model_validate(incident)
    latest = max(detail.reviews, key=lambda r: (r.created_at, r.id), default=None)
    return detail.model_copy(update={"review_label": latest.label if latest else None})


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
    user: Annotated[User | None, Depends(get_current_user)],
) -> IncidentReviewRead:
    """Submit an append-only human review decision for an incident.

    Guarantees that detector outputs (fall_score, model_name, evidence_features)
    remain completely unchanged.
    """
    review = service.submit_review(
        incident_id=incident_id,
        label=payload.label,
        notes=payload.notes,
        reviewer=payload.reviewer or (user.full_name if user is not None else None),
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
