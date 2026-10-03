"""Unit tests for API Error Model, Validation, and CORS handling (P5-004)."""

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base

sample_err_router = APIRouter()


@sample_err_router.get("/test/crash")
def crash_endpoint() -> None:
    """Simulated endpoint raising unhandled exception."""
    raise RuntimeError("Sensitive internal stack trace or DB credential failure")


@pytest.fixture
def test_client() -> TestClient:
    """Create a FastAPI test client backed by an in-memory SQLite database."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=session_factory)
    app.include_router(sample_err_router)
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    Base.metadata.drop_all(engine)


class TestAPIErrorHandling:
    """Test suite verifying standard error envelopes and security guardrails."""

    def test_validation_error_envelope(self, test_client: TestClient) -> None:
        """Verify invalid request body returns 422 with standard error envelope."""
        # Post invalid payload (missing required name field)
        res = test_client.post("/cameras", json={"id": "bad-cam"})
        assert res.status_code == 422
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "name" in data["error"]["message"]
        assert data["error"]["request_id"] is not None

    def test_internal_server_error_masks_trace(self, test_client: TestClient) -> None:
        """Verify 500 errors return sanitized error message without exposing traceback."""
        res = test_client.get("/test/crash")
        assert res.status_code == 500
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["message"] == "An internal server error occurred."
        assert "Sensitive" not in res.text
        assert "traceback" not in res.text.lower()
        assert data["error"]["request_id"] is not None

    def test_cors_headers_present(self, test_client: TestClient) -> None:
        """Verify CORS headers on OPTIONS preflight request."""
        res = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") in (
            "*",
            "http://localhost:5173",
        )

    def test_security_headers_present(self, test_client: TestClient) -> None:
        """Verify standard defensive security headers are returned on API responses."""
        res = test_client.get("/health")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
