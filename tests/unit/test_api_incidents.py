"""Unit and contract tests for Incident List, Detail, and Evidence Streaming APIs (P5-005)."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.models import Base
from eldercare.evidence.storage import EvidenceStorage
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import (
    AgentEnrichmentCreate,
    IncidentCreate,
    IncidentEvidenceCreate,
)


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
def evidence_storage(tmp_path: Path) -> EvidenceStorage:
    """Provide a temporary sandboxed evidence storage."""
    base_dir = tmp_path / "evidence_store"
    return EvidenceStorage(base_dir=base_dir)


@pytest.fixture
def client(
    test_db_session_factory: sessionmaker[Session],
    evidence_storage: EvidenceStorage,
) -> TestClient:
    """Provide FastAPI test client configured with in-memory DB and temp storage."""
    app = create_app(
        session_factory=test_db_session_factory,
        evidence_storage=evidence_storage,
    )
    return TestClient(app)


def test_list_incidents_empty(client: TestClient) -> None:
    """Verify GET /incidents returns empty paginated structure when no incidents exist."""
    response = client.get("/incidents")
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_list_incidents_filtering_and_pagination(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify incident filtering by camera_id, status, timestamps, review_label, and pagination."""
    t0 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 23, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)

    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01", name="Camera 1")
        repo.get_or_create_camera("cam-02", name="Camera 2")

        # Incident 1: cam-01, confirmed at t0
        repo.create_incident(
            IncidentCreate(
                id="inc-001",
                camera_id="cam-01",
                track_id="tr-1",
                started_at=t0,
                confirmed_at=t0,
                fall_score=0.92,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"angle": 75.0},
                detector_state="FALL_CONFIRMED",
            )
        )
        repo.add_review("inc-001", label="confirmed_fall", reviewer="nurse-1")

        # Incident 2: cam-01, confirmed at t1
        repo.create_incident(
            IncidentCreate(
                id="inc-002",
                camera_id="cam-01",
                track_id="tr-2",
                started_at=t1,
                confirmed_at=t1,
                fall_score=0.88,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"angle": 80.0},
                detector_state="FALL_COOLDOWN",
            )
        )

        # Incident 3: cam-02, confirmed at t2
        repo.create_incident(
            IncidentCreate(
                id="inc-003",
                camera_id="cam-02",
                track_id="tr-3",
                started_at=t2,
                confirmed_at=t2,
                fall_score=0.95,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"angle": 85.0},
                detector_state="FALL_CONFIRMED",
            )
        )
        session.commit()

    # 1. Total list (ordered by confirmed_at desc)
    resp = client.get("/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["id"] == "inc-003"
    assert data["items"][1]["id"] == "inc-002"
    assert data["items"][2]["id"] == "inc-001"

    # 2. Filter by camera_id
    resp_cam = client.get("/incidents?camera_id=cam-01")
    assert resp_cam.status_code == 200
    data_cam = resp_cam.json()
    assert data_cam["total"] == 2
    assert [i["id"] for i in data_cam["items"]] == ["inc-002", "inc-001"]

    # 3. Filter by status
    resp_stat = client.get("/incidents?status=FALL_COOLDOWN")
    assert resp_stat.status_code == 200
    data_stat = resp_stat.json()
    assert data_stat["total"] == 1
    assert data_stat["items"][0]["id"] == "inc-002"

    # 4. Filter by review_label
    resp_rev = client.get("/incidents?review_label=confirmed_fall")
    assert resp_rev.status_code == 200
    data_rev = resp_rev.json()
    assert data_rev["total"] == 1
    assert data_rev["items"][0]["id"] == "inc-001"

    # 5. Filter by time window (from / to)
    resp_time = client.get("/incidents?from=2026-09-23T10:30:00Z&to=2026-09-23T12:30:00Z")
    assert resp_time.status_code == 200
    data_time = resp_time.json()
    assert data_time["total"] == 2
    assert [i["id"] for i in data_time["items"]] == ["inc-003", "inc-002"]

    # 6. Pagination (limit + offset)
    resp_page = client.get("/incidents?limit=2&offset=1")
    assert resp_page.status_code == 200
    data_page = resp_page.json()
    assert data_page["total"] == 3
    assert len(data_page["items"]) == 2
    assert data_page["limit"] == 2
    assert data_page["offset"] == 1
    assert data_page["items"][0]["id"] == "inc-002"
    assert data_page["items"][1]["id"] == "inc-001"


def test_get_incident_detail_found(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify GET /incidents/{incident_id} returns all nested relation objects."""
    t_now = datetime(2026, 9, 23, 14, 0, 0, tzinfo=timezone.utc)

    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01", name="Camera 1")
        repo.create_incident(
            IncidentCreate(
                id="inc-detail-1",
                camera_id="cam-01",
                track_id="tr-42",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.965,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"drop_speed_mps": 2.4, "torso_angle_deg": 78.5},
                detector_state="FALL_CONFIRMED",
            )
        )
        repo.add_evidence(
            incident_id="inc-detail-1",
            data=IncidentEvidenceCreate(
                id="ev-01",
                evidence_type="snapshot",
                storage_path="cam-01/inc-detail-1/snap.jpg",
                mime_type="image/jpeg",
                sha256="a" * 64,
                captured_at=t_now,
            ),
        )
        repo.add_review(
            incident_id="inc-detail-1",
            label="confirmed_fall",
            notes="Subject tripped on carpet.",
            reviewer="Dr. Smith",
            review_id="rev-01",
        )
        repo.add_enrichment(
            incident_id="inc-detail-1",
            data=AgentEnrichmentCreate(
                id="enr-01",
                prompt_version="v1",
                status="completed",
                provider="gemini",
                model="gemini-2.0-flash",
                output={"narrative": "Elderly individual fell forward."},
                duration_ms=450,
                completed_at=t_now,
            ),
        )
        session.commit()

    resp = client.get("/incidents/inc-detail-1")
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == "inc-detail-1"
    assert data["camera_id"] == "cam-01"
    assert data["track_id"] == "tr-42"
    assert data["fall_score"] == 0.965
    assert data["model_name"] == "yolo26s-pose.pt"
    assert data["evidence_features"]["drop_speed_mps"] == 2.4

    # Relations
    assert len(data["evidence"]) == 1
    assert data["evidence"][0]["id"] == "ev-01"
    assert data["evidence"][0]["mime_type"] == "image/jpeg"

    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["id"] == "rev-01"
    assert data["reviews"][0]["label"] == "confirmed_fall"
    assert data["reviews"][0]["reviewer"] == "Dr. Smith"

    assert len(data["enrichments"]) == 1
    assert data["enrichments"][0]["id"] == "enr-01"
    assert data["enrichments"][0]["status"] == "completed"
    assert data["enrichments"][0]["output"]["narrative"] == "Elderly individual fell forward."


def test_get_incident_detail_not_found(client: TestClient) -> None:
    """Verify GET /incidents/{incident_id} returns 404 with structured error envelope."""
    response = client.get("/incidents/nonexistent-inc-id")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert "nonexistent-inc-id" in data["error"]["message"]
    assert data["error"]["request_id"] is not None


def test_stream_incident_evidence_success(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
    evidence_storage: EvidenceStorage,
) -> None:
    """Verify binary evidence streaming with content-type and SHA-256 headers."""
    t_now = datetime(2026, 9, 23, 15, 0, 0, tzinfo=timezone.utc)
    raw_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"

    # Save to evidence storage
    rel_path, byte_count, file_hash = evidence_storage.save_stream(
        relative_path="cam-01/inc-stream-1/snapshot.jpg",
        stream=io.BytesIO(raw_bytes),
    )

    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01")
        repo.create_incident(
            IncidentCreate(
                id="inc-stream-1",
                camera_id="cam-01",
                track_id="tr-99",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.91,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )
        )
        repo.add_evidence(
            incident_id="inc-stream-1",
            data=IncidentEvidenceCreate(
                id="ev-stream-1",
                evidence_type="snapshot",
                storage_path=rel_path,
                mime_type="image/jpeg",
                sha256=file_hash,
                captured_at=t_now,
            ),
        )
        session.commit()

    response = client.get("/incidents/inc-stream-1/evidence/ev-stream-1")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("image/jpeg")
    assert response.headers["X-Evidence-SHA256"] == file_hash
    assert response.headers["Content-Length"] == str(len(raw_bytes))
    assert response.content == raw_bytes


def test_stream_incident_evidence_not_found_records(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify 404 when incident or evidence record does not exist."""
    t_now = datetime(2026, 9, 23, 15, 0, 0, tzinfo=timezone.utc)
    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01")
        repo.create_incident(
            IncidentCreate(
                id="inc-exists",
                camera_id="cam-01",
                track_id="tr-1",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.90,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )
        )
        session.commit()

    # Incident nonexistent
    resp1 = client.get("/incidents/nonexistent/evidence/ev-1")
    assert resp1.status_code == 404
    assert resp1.json()["error"]["code"] == "INCIDENT_NOT_FOUND"

    # Evidence record nonexistent
    resp2 = client.get("/incidents/inc-exists/evidence/ev-missing")
    assert resp2.status_code == 404
    assert resp2.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


def test_stream_incident_evidence_missing_physical_file(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify 404 EVIDENCE_FILE_NOT_FOUND if evidence record exists but physical file is missing."""
    t_now = datetime(2026, 9, 23, 15, 0, 0, tzinfo=timezone.utc)
    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01")
        repo.create_incident(
            IncidentCreate(
                id="inc-nofile",
                camera_id="cam-01",
                track_id="tr-1",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.90,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )
        )
        repo.add_evidence(
            incident_id="inc-nofile",
            data=IncidentEvidenceCreate(
                id="ev-nofile",
                evidence_type="snapshot",
                storage_path="cam-01/inc-nofile/nonexistent_on_disk.jpg",
                mime_type="image/jpeg",
                sha256="b" * 64,
                captured_at=t_now,
            ),
        )
        session.commit()

    resp = client.get("/incidents/inc-nofile/evidence/ev-nofile")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EVIDENCE_FILE_NOT_FOUND"


def test_stream_incident_evidence_path_traversal_protection(
    client: TestClient,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify 400 PATH_TRAVERSAL_FORBIDDEN if a poisoned storage_path is attempted."""
    t_now = datetime(2026, 9, 23, 15, 0, 0, tzinfo=timezone.utc)
    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01")
        repo.create_incident(
            IncidentCreate(
                id="inc-poison",
                camera_id="cam-01",
                track_id="tr-1",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.90,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )
        )
        repo.add_evidence(
            incident_id="inc-poison",
            data=IncidentEvidenceCreate(
                id="ev-poison",
                evidence_type="snapshot",
                storage_path="../../etc/shadow",
                mime_type="application/octet-stream",
                sha256="c" * 64,
                captured_at=t_now,
            ),
        )
        session.commit()

    resp = client.get("/incidents/inc-poison/evidence/ev-poison")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PATH_TRAVERSAL_FORBIDDEN"


def test_incidents_api_v1_prefix(client: TestClient) -> None:
    """Verify /api/v1/incidents prefix functions identically."""
    resp = client.get("/api/v1/incidents")
    assert resp.status_code == 200
    assert "items" in resp.json()
