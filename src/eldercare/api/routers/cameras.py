"""Camera management and telemetry router (P5-004)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eldercare.api.audit import record_audit
from eldercare.api.dependencies import (
    ensure_admin,
    get_current_user,
    get_db,
    get_incident_repository,
)
from eldercare.api.schemas import CameraCreate, CameraRead, CameraUpdate
from eldercare.db.models import Camera, Incident, User
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import CameraNotFoundError

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get(
    "",
    response_model=list[CameraRead],
    summary="List Cameras",
    description="Retrieve all registered cameras with health and telemetry status.",
)
def list_cameras(
    db: Annotated[Session, Depends(get_db)],
) -> Sequence[Camera]:
    """Return all camera entities in the system.

    RTSP credentials and connection URLs are strictly omitted.
    """
    stmt = select(Camera).order_by(Camera.id.asc())
    return db.scalars(stmt).all()


@router.get(
    "/{camera_id}",
    response_model=CameraRead,
    summary="Get Camera Detail",
    description="Retrieve specific camera telemetry and operational status.",
)
def get_camera(
    camera_id: str,
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
) -> Camera:
    """Return camera metadata or raise CameraNotFoundError (404)."""
    camera = repo.get_camera(camera_id)
    if camera is None:
        raise CameraNotFoundError(camera_id)
    return camera


@router.post(
    "",
    response_model=CameraRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register Camera",
    description="Register a new camera in the persistence catalog.",
)
def create_camera(
    payload: CameraCreate,
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
    user: Annotated[User | None, Depends(get_current_user)] = None,
) -> Camera:
    """Create a new Camera record."""
    ensure_admin(user, "register cameras")
    camera = repo.get_or_create_camera(
        camera_id=payload.id,
        name=payload.name,
        status=payload.status,
    )
    camera.enabled = payload.enabled
    record_audit(db, user, "camera.created", camera.id, {"name": camera.name})
    db.commit()
    db.refresh(camera)
    return camera


@router.patch(
    "/{camera_id}",
    response_model=CameraRead,
    summary="Update Camera",
    description="Update camera configuration or operational status.",
)
def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
    user: Annotated[User | None, Depends(get_current_user)] = None,
) -> Camera:
    """Update camera parameters."""
    ensure_admin(user, "change cameras")
    camera = repo.get_camera(camera_id)
    if camera is None:
        raise CameraNotFoundError(camera_id)

    changes = payload.model_dump(exclude_none=True)
    if payload.name is not None:
        camera.name = payload.name
    if payload.enabled is not None:
        camera.enabled = payload.enabled
        manager = getattr(request.app.state, "live_manager", None)
        if not payload.enabled and manager is not None:
            manager.stop(camera_id)
    if payload.status is not None:
        camera.status = payload.status

    if changes.keys() - {"status"}:
        record_audit(db, user, "camera.updated", camera_id, changes)
    db.commit()
    db.refresh(camera)
    return camera


@router.delete(
    "/{camera_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Camera",
    description="Remove a camera that has no recorded incidents.",
)
def delete_camera(
    camera_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
    user: Annotated[User | None, Depends(get_current_user)] = None,
) -> Response:
    """Delete a camera; refuse when incidents reference it (they are evidence)."""
    if user is not None and user.role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admin role required to delete cameras.",
        )
    camera = repo.get_camera(camera_id)
    if camera is None:
        raise CameraNotFoundError(camera_id)
    has_incidents = db.scalar(
        select(func.count(Incident.id)).where(Incident.camera_id == camera_id)
    )
    if has_incidents:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This camera has recorded incidents; disable it instead of deleting it.",
        )
    manager = getattr(request.app.state, "live_manager", None)
    if manager is not None:
        manager.stop(camera_id)
    record_audit(db, user, "camera.deleted", camera_id, {"name": camera.name})
    db.delete(camera)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
