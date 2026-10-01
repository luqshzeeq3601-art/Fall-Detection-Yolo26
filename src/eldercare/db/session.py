"""Database engine, sessionmaker, and dependency injection helpers (P5-001)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(
    url: str | None = None,
    echo: bool = False,
    **kwargs: Any,
) -> Engine:
    """Create a configured SQLAlchemy engine.

    Parameters
    ----------
    url : str | None
        Database connection URL. If None, loads effective `database_url` from Settings.
    echo : bool
        If True, enables SQLAlchemy SQL query echoing.
    **kwargs : Any
        Additional keyword arguments passed to `create_engine`.

    Returns
    -------
    Engine
        Configured SQLAlchemy Engine instance.
    """
    if url is None:
        try:
            from eldercare.common.settings import Settings

            settings = Settings()
            url = settings.database_url
        except Exception:
            # Fallback to local in-memory SQLite if settings cannot be loaded
            url = "sqlite:///:memory:"

    connect_args = kwargs.pop("connect_args", {})
    if url.startswith("sqlite"):
        # SQLite specific configuration for multi-thread access
        connect_args.setdefault("check_same_thread", False)

    return create_engine(
        url,
        echo=echo,
        connect_args=connect_args,
        **kwargs,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured sessionmaker bound to the given engine.

    Parameters
    ----------
    engine : Engine
        SQLAlchemy Engine instance.

    Returns
    -------
    sessionmaker[Session]
        Configured sessionmaker instance.
    """
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )


# Module-level default engine and sessionmaker (lazy/configurable)
_DEFAULT_ENGINE: Engine | None = None
_DEFAULT_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_default_engine() -> Engine:
    """Get or initialize the module-level default engine."""
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = create_db_engine()
    return _DEFAULT_ENGINE


def get_default_session_factory() -> sessionmaker[Session]:
    """Get or initialize the module-level default sessionmaker."""
    global _DEFAULT_SESSION_FACTORY
    if _DEFAULT_SESSION_FACTORY is None:
        _DEFAULT_SESSION_FACTORY = create_session_factory(get_default_engine())
    return _DEFAULT_SESSION_FACTORY


def get_db_session(
    session_factory: sessionmaker[Session] | None = None,
) -> Generator[Session, None, None]:
    """Yield a database session context with automatic rollback on exception and cleanup.

    Parameters
    ----------
    session_factory : sessionmaker[Session] | None
        Optional explicit sessionmaker. Defaults to `get_default_session_factory()`.

    Yields
    ------
    Session
        Active database session.
    """
    factory = session_factory or get_default_session_factory()
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
