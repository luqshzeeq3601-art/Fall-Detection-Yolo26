"""Evidence retention: delete incidents (and their evidence files) older than N days."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from eldercare.common.logger import get_logger
from eldercare.db.models import Incident
from eldercare.evidence.storage import EvidenceStorage, PathTraversalError

logger = get_logger("eldercare.incidents.retention")


def purge_expired_incidents(
    session_factory: sessionmaker[Session],
    storage: EvidenceStorage,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    """Delete incidents confirmed before ``now - retention_days``; return the count."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    with session_factory() as session:
        # SQLite stores naive UTC values.
        if session.get_bind().dialect.name == "sqlite":
            cutoff = cutoff.replace(tzinfo=None)
        expired = session.scalars(
            select(Incident)
            .options(selectinload(Incident.evidence))
            .where(Incident.confirmed_at < cutoff)
        ).all()
        for incident in expired:
            for evidence in incident.evidence:
                try:
                    storage.delete_file(evidence.storage_path)
                except (PathTraversalError, OSError):
                    logger.warning("Could not delete evidence %s", evidence.id)
            session.delete(incident)
        session.commit()
    if expired:
        logger.info("Retention purge removed %d incident(s)", len(expired))
    return len(expired)
