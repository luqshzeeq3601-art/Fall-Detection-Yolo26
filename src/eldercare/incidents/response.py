"""Incident response: who is handling a confirmed fall, how it ended, and escalation.

Responses are an append-only ledger, like reviews. A review says whether the detector
was right; a response says whether someone went to help. Escalation is written by the
server when a fall goes unanswered for the workspace's configured delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from eldercare.db.models import Incident, IncidentResponse

# Video files are analysed under this camera (see eldercare.live.manager); nobody needs
# to go and help a recording, so its incidents are never escalated.
VIDEO_ANALYSIS_CAMERA_ID = "video-analysis"
# Only falls this recent are escalated, so enabling escalation never floods dashboards
# with an old backlog.
ESCALATION_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class ResponseState:
    """Current handling state derived from the ledger."""

    status: str  # open | escalated | responding | resolved
    responder: str | None = None
    outcome: str | None = None


def derive_state(rows: list[IncidentResponse]) -> ResponseState:
    """Fold ledger rows (oldest first) into the current state."""
    state = ResponseState("open")
    for row in rows:
        if row.action == "escalated":
            if state.status == "open":
                state = ResponseState("escalated")
        elif row.action == "responding":
            if state.status != "resolved":
                state = ResponseState("responding", row.responder)
        elif row.action == "resolved":
            state = ResponseState("resolved", row.responder, row.outcome)
    return state


def response_states(db: Session, incident_ids: list[str]) -> dict[str, ResponseState]:
    """Current state for each incident id (incidents without rows are ``open``)."""
    if not incident_ids:
        return {}
    rows: dict[str, list[IncidentResponse]] = {}
    for row in db.scalars(
        select(IncidentResponse)
        .where(IncidentResponse.incident_id.in_(incident_ids))
        .order_by(IncidentResponse.created_at, IncidentResponse.id)
    ):
        rows.setdefault(row.incident_id, []).append(row)
    return {incident_id: derive_state(rows.get(incident_id, [])) for incident_id in incident_ids}


def _db_time(value: datetime, db: Session) -> datetime:
    if db.get_bind().dialect.name == "sqlite":
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def escalate_unanswered(
    session_factory: sessionmaker[Session], after_sec: int, now: datetime | None = None
) -> list[tuple[str, str]]:
    """Escalate recent falls nobody has responded to; return ``(incident_id, camera_id)``.

    Each incident is escalated at most once.
    """
    now = now or datetime.now(timezone.utc)
    escalated: list[tuple[str, str]] = []
    with session_factory() as db:
        candidates = db.execute(
            select(Incident.id, Incident.camera_id)
            .where(Incident.confirmed_at >= _db_time(now - ESCALATION_WINDOW, db))
            .where(Incident.confirmed_at <= _db_time(now - timedelta(seconds=after_sec), db))
            .where(Incident.camera_id != VIDEO_ANALYSIS_CAMERA_ID)
            .where(~Incident.responses.any())
        ).all()
        for incident_id, camera_id in candidates:
            db.add(IncidentResponse(incident_id=incident_id, action="escalated", created_at=now))
            escalated.append((incident_id, camera_id))
        if escalated:
            db.commit()
    return escalated
