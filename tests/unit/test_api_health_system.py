"""Unit tests for Health, Readiness, and System Status API endpoints (P5-004)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base


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
    client = TestClient(app)
    yield client
    Base.metadata.drop_all(engine)


class TestHealthAndSystemAPI:
    """Test suite verifying health probes, readiness checks, and system telemetry."""

    def test_health_liveness_endpoints(self, test_client: TestClient) -> None:
        """Verify GET /health and GET /api/v1/health return 200 OK status."""
        for path in ("/health", "/api/v1/health"):
            res = test_client.get(path)
            assert res.status_code == 200
            assert res.json() == {"status": "ok"}
            assert "x-request-id" in res.headers

    def test_ready_readiness_probe_healthy(self, test_client: TestClient) -> None:
        """Verify GET /ready and GET /api/v1/ready return ready status when DB is connected."""
        for path in ("/ready", "/api/v1/ready"):
            res = test_client.get(path)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "ready"
            assert data["database"] == "ready"
            # This app is built without live video, so the vision service is reported off.
            assert data["vision_service"] == "disabled"

    def test_ready_probe_fails_when_db_down(self) -> None:
        """Verify GET /ready returns 503 Service Unavailable when database probe fails."""
        mock_factory = MagicMock()
        mock_session = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_session
        mock_session.execute.side_effect = RuntimeError("DB connection refused")

        app = create_app(session_factory=mock_factory)
        client = TestClient(app)

        res = client.get("/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "unavailable"

    def test_system_status_contract_and_no_secrets(self, test_client: TestClient) -> None:
        """Verify GET /system/status matches API contract and leaks no secrets."""
        for path in ("/system/status", "/api/v1/system/status"):
            res = test_client.get(path)
            assert res.status_code == 200
            data = res.json()

            assert data["version"] == "1.0.0"
            assert data["model_name"] == "yolo26s-pose.pt + v6_3_phase3b"
            assert data["model_version"] == "6.3"
            assert data["config_version"] == "frozen-v6.3"
            assert "camera_count" in data
            # No stream is running, so measured throughput is zero rather than a sample value.
            assert data["active_streams"] == 0
            assert data["vision_fps"] == 0.0
            assert "inference_latency_ms" in data
            assert "avg" in data["inference_latency_ms"]
            assert "gpu_summary" in data
            assert "device" in data["gpu_summary"]

            # Assert complete absence of passwords, tokens, or URLs
            payload_str = res.text
            assert "password" not in payload_str.lower()
            assert "rtsp" not in payload_str.lower()
            assert "secret" not in payload_str.lower()

    def test_custom_request_id_forwarded(self, test_client: TestClient) -> None:
        """Verify client-supplied X-Request-ID header is preserved in response."""
        custom_id = "test-custom-uuid-12345"
        res = test_client.get("/health", headers={"X-Request-ID": custom_id})
        assert res.status_code == 200
        assert res.headers.get("x-request-id") == custom_id
