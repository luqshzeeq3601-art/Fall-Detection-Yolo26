"""Workspace settings router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from eldercare.api.audit import record_audit
from eldercare.api.dependencies import get_current_user, get_db
from eldercare.api.workspace import (
    WorkspaceSettings,
    load_workspace_settings,
    save_workspace_settings,
)
from eldercare.db.models import User
from eldercare.live.engine import frozen_operating_point

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=dict)
def get_settings(db: Annotated[Session, Depends(get_db)]) -> dict:
    """Stored settings plus the frozen model's calibrated defaults for reference."""
    op = frozen_operating_point()
    return {
        "settings": load_workspace_settings(db).model_dump(),
        "frozen_defaults": {
            "fall_threshold": op.get("fall_trigger_threshold"),
            "min_down_sec": op.get("min_down_sustain_seconds"),
        },
    }


@router.put("", response_model=WorkspaceSettings)
def put_settings(
    payload: WorkspaceSettings,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_current_user)] = None,
) -> WorkspaceSettings:
    """Replace workspace settings. Detection/overlay changes apply on the next stream start."""
    if user is not None and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to modify workspace settings.",
        )
    before = load_workspace_settings(db).model_dump()
    after = payload.model_dump()
    changed = {key: after[key] for key in after if after[key] != before.get(key)}
    if changed:
        record_audit(db, user, "settings.updated", "workspace", changed)
    return save_workspace_settings(db, payload)
