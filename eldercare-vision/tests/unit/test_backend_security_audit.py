"""Automated Security Audit & Penetration Probes for Phase 5 Backend (P5-008)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.api.ws import ConnectionManager
from eldercare.db.models import Base, Camera
from eldercare.evidence.storage import EvidenceStorage, PathTraversalError
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import IncidentCreate, IncidentEvidenceCreate


@pytest.fixture
def test_db_session_factory():
    """Create an in-memory SQLite database sharing schema across connections."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(
    test_db_session_factory: sessionmaker[Session],
    tmp_path,
) -> TestClient:
    """Provide FastAPI test client configured with in-memory DB and storage."""
    evidence_storage = EvidenceStorage(base_dir=tmp_path / "evidence_store")
    connection_manager = ConnectionManager()
    app = create_app(
        session_factory=test_db_session_factory,
        evidence_storage=evidence_storage,
        connection_manager=connection_manager,
    )
    return TestClient(app)


@pytest.fixture
def seed_db_security(test_db_session_factory: sessionmaker[Session]) -> None:
    """Seed sample camera and incident data for security probes."""
    t_now = datetime(2026, 9, 23, 18, 0, 0, tzinfo=timezone.utc)
    with test_db_session_factory() as session:
        cam = Camera(
            id="cam-secure-01",
            name="Living Room Secure Cam",
            status="online",
            enabled=True,
        )
        session.add(cam)
        session.flush()

        repo = IncidentRepository(session)
        repo.create_incident(
            IncidentCreate(
                id="inc-sec-01",
                camera_id="cam-secure-01",
                track_id="tr-1",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.97,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"feature": "value"},
            )
        )
        repo.add_evidence(
            incident_id="inc-sec-01",
            data=IncidentEvidenceCreate(
                id="ev-sec-01",
                evidence_type="snapshot",
                storage_path="cam-secure-01/inc-sec-01/frame.jpg",
                mime_type="image/jpeg",
                sha256="d" * 64,
                captured_at=t_now,
            ),
        )
        session.commit()


# ==============================================================================
# 1. SQL Injection Resistance Probes
# ==============================================================================


@pytest.mark.parametrize(
    "sqli_payload",
    [
        "' OR '1'='1",
        "'; DROP TABLE incidents; --",
        "1 UNION SELECT null, null, null, null, null, null, null, null, null, null, null, null --",
        "' OR 1=1 #",
        "admin'--",
    ],
)
def test_sqli_incident_list_filtering(
    client: TestClient, seed_db_security: None, sqli_payload: str
) -> None:
    """Verify SQL injection payloads in query filters are safely parameterized."""
    resp = client.get(f"/incidents?camera_id={sqli_payload}")
    assert resp.status_code == 200
    data = resp.json()
    # Should safely return 0 matches rather than leaking data or raising DB syntax errors
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.parametrize(
    "sqli_payload",
    [
        "' OR '1'='1",
        "nonexistent' UNION SELECT id, name FROM cameras --",
    ],
)
def test_sqli_camera_lookup(client: TestClient, seed_db_security: None, sqli_payload: str) -> None:
    """Verify SQL injection payloads in camera path parameters safely return 404."""
    resp = client.get(f"/cameras/{sqli_payload}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CAMERA_NOT_FOUND"


# ==============================================================================
# 2. Path Traversal & Filesystem Sandboxing Probes
# ==============================================================================


@pytest.mark.parametrize(
    "traversal_path",
    [
        "../../etc/passwd",
        "..\\..\\Windows\\System32\\calc.exe",
        "/etc/shadow",
        "C:\\boot.ini",
        "cam-01/../../../secret.key",
        "cam-01/\x00secret.jpg",
    ],
)
def test_evidence_storage_path_traversal_rejection(tmp_path, traversal_path: str) -> None:
    """Verify EvidenceStorage strictly blocks all directory traversal patterns."""
    storage = EvidenceStorage(base_dir=tmp_path / "evidence_store")
    with pytest.raises((PathTraversalError, ValueError)):
        storage.resolve_safe_path(traversal_path)


# ==============================================================================
# 3. Secret & Credential Redaction Probes
# ==============================================================================


def test_rtsp_credentials_never_exposed_in_camera_list(
    client: TestClient, seed_db_security: None
) -> None:
    """Verify raw RTSP URL and embedded credentials never leak in GET /cameras."""
    resp = client.get("/cameras")
    assert resp.status_code == 200
    raw_text = resp.text
    assert "P@ssw0rd123!" not in raw_text
    assert "rtsp://" not in raw_text
    assert "rtsp_url" not in raw_text


def test_rtsp_credentials_never_exposed_in_camera_detail(
    client: TestClient, seed_db_security: None
) -> None:
    """Verify raw RTSP URL and credentials never leak in GET /cameras/{id}."""
    resp = client.get("/cameras/cam-secure-01")
    assert resp.status_code == 200
    raw_text = resp.text
    assert "P@ssw0rd123!" not in raw_text
    assert "rtsp://" not in raw_text
    assert "rtsp_url" not in raw_text


def test_system_status_exposes_no_secrets(client: TestClient) -> None:
    """Verify GET /system/status exposes zero credentials or sensitive strings."""
    resp = client.get("/system/status")
    assert resp.status_code == 200
    raw_text = resp.text
    assert "password" not in raw_text.lower()
    assert "secret" not in raw_text.lower()
    assert "token" not in raw_text.lower()


# ==============================================================================
# 4. Standard Error Handling & Stack-Trace Suppression Probes
# ==============================================================================


def test_unhandled_exception_does_not_leak_stacktrace(
    test_db_session_factory: sessionmaker[Session],
    tmp_path,
) -> None:
    """Verify unexpected 500 exceptions return safe message with zero Python traceback."""
    evidence_storage = EvidenceStorage(base_dir=tmp_path / "evidence_store")
    app = create_app(
        session_factory=test_db_session_factory,
        evidence_storage=evidence_storage,
    )

    # Intentionally mount a buggy test route that raises an unhandled exception
    buggy_router = APIRouter()

    @buggy_router.get("/buggy-route")
    def buggy_endpoint():
        raise ZeroDivisionError("Sensitive internal division error in proprietary engine")

    app.include_router(buggy_router)
    buggy_client = TestClient(app, raise_server_exceptions=False)

    resp = buggy_client.get("/buggy-route")
    assert resp.status_code == 500
    data = resp.json()

    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An internal server error occurred."
    assert "ZeroDivisionError" not in resp.text
    assert "Traceback" not in resp.text
    assert "proprietary engine" not in resp.text
    assert data["error"]["request_id"] is not None


# ==============================================================================
# 5. Input Validation & Injection Bounds
# ==============================================================================


def test_review_payload_field_injection_prevention(
    client: TestClient, seed_db_security: None
) -> None:
    """Verify injection of forbidden properties into review requests is strictly blocked."""
    injected_payload = {
        "label": "confirmed_fall",
        "notes": "Legitimate note",
        "admin": True,
        "role": "superuser",
        "fall_score": 0.0,
    }
    resp = client.post("/incidents/inc-sec-01/reviews", json=injected_payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
