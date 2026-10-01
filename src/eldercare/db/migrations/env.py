"""Alembic environment configuration for ElderCare Vision (P5-001)."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import eldercare.db.models  # noqa: F401

# Import the application's models and Base metadata
from eldercare.db.base import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging, preserving existing application loggers
if config.config_file_name is not None and config.attributes.get("configure_logger", False):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


target_metadata = Base.metadata


def get_url() -> str:
    """Get the database URL from environment or configuration."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    try:
        from eldercare.common.settings import Settings

        return Settings().database_url
    except Exception:
        return config.get_main_option("sqlalchemy.url", "sqlite:///:memory:")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    url = get_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=url.startswith("sqlite"),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
