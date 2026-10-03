"""Admin activity log (read-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eldercare.api.dependencies import ensure_admin, get_current_user, get_db
from eldercare.db.models import AuditEvent, User

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditEventRead(BaseModel):
    id: str
    actor: str | None
    action: str
    target: str | None
    detail: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int


@router.get("", response_model=AuditPage)
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: Annotated[User | None, Depends(get_current_user)] = None,
) -> AuditPage:
    """Newest first: settings, camera, team, export and retention changes."""
    ensure_admin(user, "view the activity log")
    total = db.scalar(select(func.count(AuditEvent.id))) or 0
    rows = db.scalars(
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return AuditPage(
        items=[AuditEventRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
