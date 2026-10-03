"""Administrative audit log: who changed settings, cameras, team members or exported data."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from eldercare.db.models import AuditEvent, User


def record_audit(
    db: Session,
    actor: User | str | None,
    action: str,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the caller's transaction (the caller commits).

    ``actor`` is the signed-in user, ``"system"`` for background jobs, or None when
    authentication is disabled.
    """
    name = actor.full_name if isinstance(actor, User) else actor
    db.add(AuditEvent(actor=name, action=action, target=target, detail=detail or None))
