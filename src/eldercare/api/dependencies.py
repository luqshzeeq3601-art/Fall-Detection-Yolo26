"""FastAPI dependency injection providers (P5-004)."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from eldercare.api.auth import SESSION_COOKIE, user_for_token
from eldercare.api.ws import ConnectionManager
from eldercare.db.models import User
from eldercare.evidence.storage import EvidenceStorage
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.service import IncidentService

if TYPE_CHECKING:
    from eldercare.live.manager import LiveManager


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a database session bound to the request lifecycle."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_incident_repository(
    db: Annotated[Session, Depends(get_db)],
) -> IncidentRepository:
    """Provide an IncidentRepository instance bound to the active request DB session."""
    return IncidentRepository(db)


def get_incident_service(request: Request) -> IncidentService:
    """Provide an IncidentService instance configured with application session factory."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    return IncidentService(session_factory)


def get_evidence_storage(request: Request) -> EvidenceStorage:
    """Provide the configured EvidenceStorage instance."""
    return request.app.state.evidence_storage


def get_connection_manager(request: Request) -> ConnectionManager:
    """Provide the application WebSocket ConnectionManager instance."""
    return request.app.state.connection_manager


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """Return the signed-in user from the session cookie, or None."""
    return user_for_token(db, request.cookies.get(SESSION_COOKIE))


def ensure_admin(user: User | None, action: str) -> None:
    """Reject a signed-in non-admin. ``user`` is None only when auth is disabled (tests/demo)."""
    if user is not None and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Admin role required to {action}."
        )


def require_user(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
) -> User | None:
    """Reject unauthenticated requests when the app was created with ``require_auth``."""
    if user is None and getattr(request.app.state, "require_auth", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    return user


def get_live_manager(request: Request) -> LiveManager:
    """Provide the live stream manager, or 503 when live video is not enabled."""
    manager: LiveManager | None = getattr(request.app.state, "live_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Live video is not enabled on this server.",
        )
    return manager
