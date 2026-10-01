"""Unit tests for Camera API endpoints and credential protection (P5-004)."""

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


class TestCameraAPI:
    """Test suite verifying camera listing, details, registration, and secret safety."""

    def test_camera_crud_and_error_contract(self, test_client: TestClient) -> None:
        """Verify camera registration, retrieval, listing, update, and 404 error envelope."""
        # 1. Initially empty list
        res = test_client.get("/api/v1/cameras")
        assert res.status_code == 200
        assert res.json() == []

        # 2. Register camera
        cam_payload = {
            "id": "cam-living-room",
            "name": "Living Room Cam",
            "enabled": True,
            "status": "online",
        }
        res = test_client.post("/api/v1/cameras", json=cam_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["id"] == "cam-living-room"
        assert data["name"] == "Living Room Cam"
        assert data["status"] == "online"
        assert data["reconnect_count"] == 0

        # 3. Retrieve camera by ID
        res = test_client.get("/api/v1/cameras/cam-living-room")
        assert res.status_code == 200
        assert res.json()["name"] == "Living Room Cam"

        # 4. Update camera
        update_payload = {"name": "Living Room Main Cam", "status": "stalled"}
        res = test_client.patch("/api/v1/cameras/cam-living-room", json=update_payload)
        assert res.status_code == 200
        assert res.json()["name"] == "Living Room Main Cam"
        assert res.json()["status"] == "stalled"

        # 5. Non-existent camera returns 404 with standard error envelope
        res = test_client.get("/api/v1/cameras/cam-does-not-exist")
        assert res.status_code == 404
        err_data = res.json()
        assert "error" in err_data
        assert err_data["error"]["code"] == "CAMERA_NOT_FOUND"
        assert "cam-does-not-exist" in err_data["error"]["message"]
        assert err_data["error"]["request_id"] is not None

    def test_rtsp_url_never_exposed_in_camera_responses(self, test_client: TestClient) -> None:
        """Verify RTSP URLs are strictly omitted from camera endpoints."""
        test_client.post(
            "/cameras",
            json={"id": "cam-secret-test", "name": "Secret Camera", "status": "online"},
        )

        res_list = test_client.get("/cameras")
        res_detail = test_client.get("/cameras/cam-secret-test")

        for res in (res_list, res_detail):
            assert res.status_code == 200
            text = res.text.lower()
            assert "rtsp" not in text
            assert "password" not in text
            assert "url" not in text
