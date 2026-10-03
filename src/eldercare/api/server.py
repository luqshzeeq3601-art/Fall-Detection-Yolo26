"""Runnable API server: ``uvicorn eldercare.api.server:create_server_app --factory``.

Enables operator sign-in and live video. Data lives in ``ELDERCARE_DATA_DIR``
(default ``demo_data/``, shared with the Streamlit demo). Without ``DATABASE_URL``
or ``POSTGRES_*`` settings it uses SQLite in that directory and creates tables on start;
PostgreSQL deployments use Alembic migrations instead.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from eldercare.api.app import create_app
from eldercare.db.base import Base
from eldercare.db.session import create_db_engine, create_session_factory

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _database_url(data_dir: Path) -> tuple[str, bool]:
    """Return (url, is_local_sqlite)."""
    if os.getenv("DATABASE_URL") or os.getenv("POSTGRES_USER"):
        from eldercare.common.settings import Settings

        return Settings().database_url, False
    return f"sqlite:///{(data_dir / 'eldercare_demo.db').as_posix()}", True


def create_server_app() -> FastAPI:
    data_dir = Path(os.getenv("ELDERCARE_DATA_DIR", str(PROJECT_ROOT / "demo_data"))).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    url, local = _database_url(data_dir)
    engine = create_db_engine(url)
    if local:
        Base.metadata.create_all(engine)
    sample_dir = Path(os.getenv("ELDERCARE_SAMPLE_DIR", str(PROJECT_ROOT / "datasets/raw/urfd")))
    origins = [o.strip() for o in os.getenv("ELDERCARE_CORS_ORIGINS", "").split(",") if o.strip()]
    return create_app(
        session_factory=create_session_factory(engine),
        evidence_dir=data_dir / "evidence",
        cors_origins=origins or ["http://127.0.0.1:5173", "http://localhost:5173"],
        require_auth=os.getenv("ELDERCARE_REQUIRE_AUTH", "true").strip().lower() != "false",
        upload_dir=data_dir / "uploads",
        sample_dir=sample_dir if sample_dir.is_dir() else None,
    )
