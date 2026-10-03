"""Incident responses (who is handling a fall, escalation) and the admin audit log.

Revision ID: 0003_responses_audit
Revises: 0002_accounts_sources_settings
Create Date: 2026-10-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_responses_audit"
down_revision: str | None = "0002_accounts_sources_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incident_responses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("responder", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_responses_incident_id_incidents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_responses")),
    )
    op.create_index(
        "ix_incident_responses_incident", "incident_responses", ["incident_id", "created_at"]
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_created", "audit_events", [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_incident_responses_incident", table_name="incident_responses")
    op.drop_table("incident_responses")
