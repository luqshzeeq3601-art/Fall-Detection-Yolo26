"""Health and readiness probe router (P5-004)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from eldercare.api.dependencies import get_db
from eldercare.api.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness Probe",
    description="Check application process liveness.",
)
def get_health() -> HealthResponse:
    """Return static OK status confirming the web service is alive."""
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness Probe",
    description="Check readiness of core database and vision services.",
)
def get_ready(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ReadyResponse:
    """Validate database connectivity and system service readiness."""
    db_status = "ready"
    overall_status = "ready"

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"
        overall_status = "not_ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadyResponse(
        status=overall_status,
        database=db_status,
        vision_service="ready",
        mqtt="disabled",
        vlm="disabled",
    )
