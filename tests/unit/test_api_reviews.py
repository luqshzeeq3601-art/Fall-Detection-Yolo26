"""Unit and contract tests for the Append-Only Incident Review API (P5-006)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.models import Base, Incident
from eldercare.evidence.storage import EvidenceStorage
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import IncidentCreate


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
    """Provide FastAPI test client configured with in-memory DB."""
    evidence_storage = EvidenceStorage(base_dir=tmp_path / "evidence_store")
    app = create_app(
        session_factory=test_db_session_factory,
        evidence_storage=evidence_storage,
    )
    return TestClient(app)


@pytest.fixture
def seed_incident(test_db_session_factory: sessionmaker[Session]) -> str:
    """Seed a test camera and incident into the database."""
    incident_id = "inc-rev-test-01"
    t_now = datetime(2026, 9, 23, 16, 0, 0, tzinfo=timezone.utc)
    with test_db_session_factory() as session:
        repo = IncidentRepository(session)
        repo.get_or_create_camera("cam-01", name="Camera Alpha")
        repo.create_incident(
            IncidentCreate(
                id=incident_id,
                camera_id="cam-01",
                track_id="tr-88",
                started_at=t_now,
                confirmed_at=t_now,
                fall_score=0.942,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={"angle": 79.2, "velocity": 2.1},
                detector_state="FALL_CONFIRMED",
            )
        )
        session.commit()
    return incident_id


def test_submit_review_success(client: TestClient, seed_incident: str) -> None:
    """Verify POST /incidents/{incident_id}/reviews creates review and returns 201."""
    payload = {
        "label": "confirmed_fall",
        "notes": "Fall confirmed by floor nurse. Patient helped up safely.",
        "reviewer": "Nurse Jackie",
    }
    response = client.post(f"/incidents/{seed_incident}/reviews", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["incident_id"] == seed_incident
    assert data["label"] == "confirmed_fall"
    assert data["notes"] == "Fall confirmed by floor nurse. Patient helped up safely."
    assert data["reviewer"] == "Nurse Jackie"
    assert "id" in data
    assert "created_at" in data


def test_submit_multiple_reviews_append_only_history(
    client: TestClient,
    seed_incident: str,
) -> None:
    """Verify multiple reviews create a chronological audit ledger without overwriting."""
    # 1. Initial triage review
    r1 = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={"label": "uncertain", "notes": "Checking sensor telemetry", "reviewer": "Triage 1"},
    )
    assert r1.status_code == 201

    # 2. Secondary physician review
    r2 = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={
            "label": "confirmed_fall",
            "notes": "Verified on video clip",
            "reviewer": "Dr. House",
        },
    )
    assert r2.status_code == 201

    # 3. Retrieve incident review list
    list_resp = client.get(f"/incidents/{seed_incident}/reviews")
    assert list_resp.status_code == 200
    reviews = list_resp.json()
    assert len(reviews) == 2
    assert reviews[0]["label"] == "uncertain"
    assert reviews[0]["reviewer"] == "Triage 1"
    assert reviews[1]["label"] == "confirmed_fall"
    assert reviews[1]["reviewer"] == "Dr. House"

    # 4. Also check full incident detail
    detail_resp = client.get(f"/incidents/{seed_incident}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert len(detail_data["reviews"]) == 2


def test_submit_review_preserves_detector_immutability(
    client: TestClient,
    seed_incident: str,
    test_db_session_factory: sessionmaker[Session],
) -> None:
    """Verify that human reviews NEVER alter algorithmic detector outputs in DB."""
    # Capture original detector fields directly from DB
    with test_db_session_factory() as session:
        orig = session.get(Incident, seed_incident)
        assert orig is not None
        orig_score = orig.fall_score
        orig_model = orig.model_name
        orig_model_ver = orig.model_version
        orig_cfg_ver = orig.config_version
        orig_features = dict(orig.evidence_features)
        orig_state = orig.detector_state

    # Submit review
    resp = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={
            "label": "non_fall",
            "notes": "False alarm - person bent down.",
            "reviewer": "Nurse Joy",
        },
    )
    assert resp.status_code == 201

    # Re-verify DB state
    with test_db_session_factory() as session:
        post = session.get(Incident, seed_incident)
        assert post is not None
        assert post.fall_score == orig_score
        assert post.model_name == orig_model
        assert post.model_version == orig_model_ver
        assert post.config_version == orig_cfg_ver
        assert post.evidence_features == orig_features
        assert post.detector_state == orig_state


def test_submit_review_invalid_label_rejected(client: TestClient, seed_incident: str) -> None:
    """Verify submitting an unknown label returns HTTP 422 validation error."""
    response = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={"label": "definitely_not_a_valid_label", "notes": "test"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_submit_review_incident_not_found(client: TestClient) -> None:
    """Verify submitting a review for a non-existent incident returns HTTP 404."""
    response = client.post(
        "/incidents/nonexistent-inc-id/reviews",
        json={"label": "confirmed_fall"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INCIDENT_NOT_FOUND"
    assert "nonexistent-inc-id" in data["error"]["message"]


def test_submit_review_notes_length_validation(client: TestClient, seed_incident: str) -> None:
    """Verify notes exceeding 2000 characters are rejected with 422."""
    huge_notes = "X" * 2001
    response = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={"label": "confirmed_fall", "notes": huge_notes},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_review_extra_fields_forbidden(client: TestClient, seed_incident: str) -> None:
    """Verify extra payload fields (e.g. attempting to inject fall_score) are forbidden."""
    response = client.post(
        f"/incidents/{seed_incident}/reviews",
        json={"label": "confirmed_fall", "fall_score": 0.0},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reviews_api_v1_prefix(client: TestClient, seed_incident: str) -> None:
    """Verify review endpoints are accessible under /api/v1/incidents prefix."""
    response = client.post(
        f"/api/v1/incidents/{seed_incident}/reviews",
        json={"label": "confirmed_fall"},
    )
    assert response.status_code == 201

    list_resp = client.get(f"/api/v1/incidents/{seed_incident}/reviews")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1
