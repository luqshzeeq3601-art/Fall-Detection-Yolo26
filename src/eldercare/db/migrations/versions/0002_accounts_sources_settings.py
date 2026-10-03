"""Operator accounts, login sessions, camera sources and workspace settings.

Revision ID: 0002_accounts_sources_settings
Revises: 0001_initial_schema
Create Date: 2026-10-02 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_accounts_sources_settings"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "camera_sources",
        sa.Column("camera_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("room", sa.String(length=128), nullable=True),
        sa.Column("loop", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["camera_id"],
            ["cameras.id"],
            name=op.f("fk_camera_sources_camera_id_cameras"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("camera_id", name=op.f("pk_camera_sources")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="operator", nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column("care_setting", sa.String(length=64), nullable=True),
        sa.Column("job_role", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_user_sessions")),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("user_sessions")
    op.drop_table("users")
    op.drop_table("camera_sources")
