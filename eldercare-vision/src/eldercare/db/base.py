"""Database declarative base and metadata configuration for ElderCare Vision (P5-001)."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Standard naming conventions for automated Alembic constraint generation
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative Base for all ElderCare Vision persistence models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
