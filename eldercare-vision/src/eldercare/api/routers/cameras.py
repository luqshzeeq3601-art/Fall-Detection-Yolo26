"""Camera management and telemetry router (P5-004)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from eldercare.api.dependencies import get_db, get_incident_repository
from eldercare.api.schemas import CameraCreate, CameraRead, CameraUpdate
from eldercare.db.models import Camera
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
) -> Camera:
    """Create a new Camera record."""
    camera = repo.get_or_create_camera(
        camera_id=payload.id,
        name=payload.name,
        status=payload.status,
    )
    camera.enabled = payload.enabled
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
    db: Annotated[Session, Depends(get_db)],
    repo: Annotated[IncidentRepository, Depends(get_incident_repository)],
) -> Camera:
    """Update camera parameters."""
    camera = repo.get_camera(camera_id)
    if camera is None:
        raise CameraNotFoundError(camera_id)

    if payload.name is not None:
        camera.name = payload.name
    if payload.enabled is not None:
        camera.enabled = payload.enabled
    if payload.status is not None:
        camera.status = payload.status

    db.commit()
    db.refresh(camera)
    return camera
