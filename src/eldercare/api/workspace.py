"""Persisted workspace settings (detection overrides, overlay, alerts, retention, export)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from eldercare.db.models import AppSetting

SETTINGS_KEY = "workspace"


class WorkspaceSettings(BaseModel):
    """Operator-editable settings. ``None`` detection values keep the frozen calibration."""

    fall_threshold: float | None = Field(default=None, ge=0.2, le=0.8)
    min_down_sec: float | None = Field(default=None, ge=0.1, le=1.5)
    show_skeleton: bool = True
    show_bbox: bool = True
    blur_faces: bool = False
    browser_alerts: bool = True
    alert_sound: bool = True
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    export_include_uncertain: bool = False

    model_config = ConfigDict(extra="forbid")


def load_workspace_settings(session: Session) -> WorkspaceSettings:
    """Return stored settings, falling back to defaults for missing or invalid rows."""
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        return WorkspaceSettings()
    try:
        return WorkspaceSettings.model_validate(row.value)
    except ValueError:
        return WorkspaceSettings()


def save_workspace_settings(session: Session, settings: WorkspaceSettings) -> WorkspaceSettings:
    """Upsert the settings row and commit."""
    row = session.get(AppSetting, SETTINGS_KEY)
    value = settings.model_dump()
    if row is None:
        session.add(AppSetting(key=SETTINGS_KEY, value=value))
    else:
        row.value = value
    session.commit()
    return settings
