"""FastAPI dependency injection providers (P5-004)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from eldercare.evidence.storage import EvidenceStorage
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.service import IncidentService


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
