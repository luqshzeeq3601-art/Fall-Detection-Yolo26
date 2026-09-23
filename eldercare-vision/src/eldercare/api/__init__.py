"""ElderCare Vision FastAPI REST API subpackage."""

from eldercare.api.app import create_app
from eldercare.api.schemas import (
    CameraCreate,
    CameraRead,
    CameraUpdate,
    ErrorDetail,
    ErrorResponse,
    GpuSummary,
    HealthResponse,
    IncidentDetailRead,
    IncidentEvidenceRead,
    IncidentFilter,
    IncidentRead,
    IncidentReviewCreate,
    IncidentReviewRead,
    LatencySummary,
    PaginatedIncidents,
    ReadyResponse,
    SystemStatusResponse,
    WebSocketEvent,
)
from eldercare.api.ws import ConnectionManager

__all__ = [
    "CameraCreate",
    "CameraRead",
    "CameraUpdate",
    "ConnectionManager",
    "ErrorDetail",
    "ErrorResponse",
    "GpuSummary",
    "HealthResponse",
    "IncidentDetailRead",
    "IncidentEvidenceRead",
    "IncidentFilter",
    "IncidentRead",
    "IncidentReviewCreate",
    "IncidentReviewRead",
    "LatencySummary",
    "PaginatedIncidents",
    "ReadyResponse",
    "SystemStatusResponse",
    "WebSocketEvent",
    "create_app",
]
