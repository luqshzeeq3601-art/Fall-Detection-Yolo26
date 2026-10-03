"""Incident responses and escalation, real-world accuracy, the admin audit log, and
per-camera setup (configured webcams and sensitivity overrides)."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base
from eldercare.db.models import Camera, CameraSource, Incident, IncidentReview
from eldercare.incidents.response import escalate_unanswered, response_states

ADMIN = {"full_name": "Ada Admin", "email": "ada@example.test", "password": "secure123"}
CARER = {"full_name": "Casey Carer", "email": "casey@example.test", "password": "secure123"}


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(session_factory: sessionmaker[Session], tmp_path: Path) -> TestClient:
    app = create_app(
        session_factory=session_factory,
        evidence_dir=tmp_path / "evidence",
        vlm_provider=None,
        require_auth=True,
    )
    return TestClient(app)


def _incident(db: Session, camera_id: str, confirmed: datetime, label: str | None = None) -> str:
    if db.get(Camera, camera_id) is None:
        db.add(Camera(id=camera_id, name=camera_id.title()))
    incident = Incident(
        camera_id=camera_id,
        track_id="1",
        started_at=confirmed,
        confirmed_at=confirmed,
        detector_state="FALL_CONFIRMED",
        fall_score=0.9,
        model_name="v6_3_phase3b",
        model_version="6.3",
        config_version="test",
        evidence_features={},
    )
    db.add(incident)
    db.flush()
    if label:
        db.add(IncidentReview(incident_id=incident.id, label=label, reviewer="Ada Admin"))
    db.commit()
    return incident.id


def _sign_in(client: TestClient, account: dict[str, str]) -> None:
    client.post("/api/v1/auth/logout")
    login = {"email": account["email"], "password": account["password"]}
    assert client.post("/api/v1/auth/login", json=login).status_code == 200


def _setup_team(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=ADMIN)
    client.post("/api/v1/auth/users", json=CARER)


def test_caregiver_responds_and_resolves(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _setup_team(client)
    with session_factory() as db:
        incident_id = _incident(db, "hall", datetime.now(timezone.utc))
    _sign_in(client, CARER)
    url = f"/api/v1/incidents/{incident_id}/responses"

    assert client.post(url, json={"action": "resolved"}).status_code == 422  # outcome required
    bad = {"action": "responding", "outcome": "resident_ok"}
    assert client.post(url, json=bad).status_code == 422
    assert client.post(url, json={"action": "responding"}).json()["responder"] == "Casey Carer"
    item = client.get("/api/v1/incidents").json()["items"][0]
    assert (item["response_status"], item["responder"]) == ("responding", "Casey Carer")

    resolve = {"action": "resolved", "outcome": "needed_help", "notes": "Helped up, no injury"}
    assert client.post(url, json=resolve).status_code == 201
    detail = client.get(f"/api/v1/incidents/{incident_id}").json()
    assert detail["response_status"] == "resolved"
    assert detail["response_outcome"] == "needed_help"
    assert [r["action"] for r in detail["responses"]] == ["responding", "resolved"]


def test_unanswered_falls_escalate_once(session_factory: sessionmaker[Session]) -> None:
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        waiting = _incident(db, "hall", now - timedelta(minutes=5))
        fresh = _incident(db, "hall", now - timedelta(seconds=20))
        _incident(db, "video-analysis", now - timedelta(minutes=5))  # a recording, not a room
        _incident(db, "hall", now - timedelta(hours=3))  # old backlog stays quiet

    assert escalate_unanswered(session_factory, 120, now) == [(waiting, "hall")]
    assert escalate_unanswered(session_factory, 120, now) == []
    with session_factory() as db:
        states = response_states(db, [waiting, fresh])
    assert states[waiting].status == "escalated"
    assert states[fresh].status == "open"


def test_real_world_accuracy_counts_reviews_by_camera(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _setup_team(client)
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        _incident(db, "hall", now - timedelta(days=1), "confirmed_fall")
        _incident(db, "hall", now - timedelta(days=2), "non_fall")
        _incident(db, "bedroom", now - timedelta(days=3), "confirmed_fall")
        _incident(db, "bedroom", now - timedelta(days=3))
        _incident(db, "video-analysis", now, "non_fall")
        _incident(db, "hall", now - timedelta(days=60), "non_fall")

    body = client.get("/api/v1/incidents/accuracy?days=30").json()
    assert (body["alerts"], body["real_falls"], body["false_alarms"]) == (4, 2, 1)
    assert body["not_reviewed"] == 1
    assert body["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert {c["camera_id"]: c["alerts"] for c in body["cameras"]} == {"hall": 2, "bedroom": 2}

    _sign_in(client, CARER)
    assert client.get("/api/v1/incidents/accuracy").status_code == 403


def test_admin_changes_are_audited(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _setup_team(client)
    with session_factory() as db:
        db.add(Camera(id="hall", name="Hall"))
        db.commit()
    assert client.put("/api/v1/settings", json={"fall_threshold": 0.6}).status_code == 200
    assert client.patch("/api/v1/cameras/hall", json={"name": "Hallway"}).status_code == 200
    client.get("/api/v1/incidents/export.jsonl")

    events = client.get("/api/v1/audit").json()["items"]
    actions = [e["action"] for e in events]
    assert actions[:3] == ["dataset.exported", "camera.updated", "settings.updated"]
    assert "member.added" in actions
    assert events[2]["detail"] == {"fall_threshold": 0.6}
    assert all(e["actor"] == "Ada Admin" for e in events)

    _sign_in(client, CARER)
    assert client.get("/api/v1/audit").status_code == 403


def test_configured_webcam_files_incidents_under_its_room(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    app = create_app(
        session_factory=session_factory,
        evidence_dir=tmp_path / "evidence",
        vlm_provider=None,
        upload_dir=tmp_path / "uploads",
    )
    with session_factory() as db:
        db.add(Camera(id="cam-living", name="Living room"))
        db.add(CameraSource(camera_id="cam-living", source_type="webcam", source="0"))
        db.commit()
    with TestClient(app):
        manager = app.state.live_manager
        assert manager.camera_for_source("webcam", "0") == "cam-living"
        assert manager.camera_for_source("webcam", "1") == "webcam-1"


def test_per_camera_sensitivity_round_trips(client: TestClient) -> None:
    _setup_team(client)
    settings = client.get("/api/v1/settings").json()["settings"]
    assert settings["escalate_after_sec"] == 120
    settings["camera_sensitivity"] = {"hall": {"fall_threshold": 0.7, "min_down_sec": None}}
    assert client.put("/api/v1/settings", json=settings).status_code == 200
    stored = client.get("/api/v1/settings").json()["settings"]["camera_sensitivity"]
    assert stored == {"hall": {"fall_threshold": 0.7, "min_down_sec": None}}
    settings["camera_sensitivity"] = {"hall": {"fall_threshold": 0.95}}
    assert client.put("/api/v1/settings", json=settings).status_code == 422
