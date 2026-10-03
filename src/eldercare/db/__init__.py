"""Database models, base, and session management package (P5-001)."""

from eldercare.db.base import Base
from eldercare.db.models import (
    AgentEnrichment,
    AppSetting,
    Camera,
    CameraSource,
    Incident,
    IncidentEvidence,
    IncidentReview,
    User,
    UserSession,
)
from eldercare.db.session import (
    create_db_engine,
    create_session_factory,
    get_db_session,
    get_default_engine,
    get_default_session_factory,
)

__all__ = [
    "AgentEnrichment",
    "AppSetting",
    "Base",
    "Camera",
    "CameraSource",
    "Incident",
    "IncidentEvidence",
    "IncidentReview",
    "User",
    "UserSession",
    "create_db_engine",
    "create_session_factory",
    "get_db_session",
    "get_default_engine",
    "get_default_session_factory",
]
