"""Live-source management: dataset labels, uploads, auto camera rows, review labels."""

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.db.base import Base
from eldercare.db.models import Camera, Incident


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(session_factory: sessionmaker[Session], tmp_path: Path) -> Iterator[TestClient]:
    samples = tmp_path / "samples"
    samples.mkdir()
    for name in ("fall-01-cam0.mp4", "adl-01-cam0.mp4", "notes.txt"):
        (samples / name).write_bytes(b"0")
    app = create_app(
        session_factory=session_factory,
        evidence_dir=tmp_path / "evidence",
        vlm_provider=None,
        upload_dir=tmp_path / "uploads",
        sample_dir=samples,
    )
    with TestClient(app) as test_client:
        yield test_client


def test_sources_label_dataset_clips_by_expected_outcome(client: TestClient) -> None:
    files = {f["name"]: f for f in client.get("/api/v1/live/sources").json()["files"]}
    assert set(files) == {"fall-01-cam0.mp4", "adl-01-cam0.mp4"}  # non-video ignored
    assert files["fall-01-cam0.mp4"]["expected"] == "fall"
    assert files["adl-01-cam0.mp4"]["expected"] == "no_fall"


def test_upload_then_delete(client: TestClient) -> None:
    created = client.post(
        "/api/v1/live/uploads", files={"file": ("kitchen.mp4", b"fake-video", "video/mp4")}
    )
    assert created.status_code == 201
    assert created.json()["ref"] == "upload:kitchen.mp4"
    names = [f["name"] for f in client.get("/api/v1/live/sources").json()["files"]]
    assert "kitchen.mp4" in names
    assert client.delete("/api/v1/live/uploads/kitchen.mp4").status_code == 204
    assert client.delete("/api/v1/live/uploads/kitchen.mp4").status_code == 404
    assert client.delete("/api/v1/live/uploads/..%2Fsecret.mp4").status_code in {400, 404}
    rejected = client.post(
        "/api/v1/live/uploads", files={"file": ("payload.exe", b"x", "application/octet-stream")}
    )
    assert rejected.status_code == 400


def test_sources_map_to_auto_created_cameras(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    manager = client.app.state.live_manager  # type: ignore[attr-defined]
    assert manager.camera_for_source("webcam", "1") == "webcam-1"
    assert manager.camera_for_source("file", "sample:fall-01-cam0.mp4") == "video-analysis"
    assert manager.camera_for_source("file", "sample:adl-01-cam0.mp4") == "video-analysis"
    with session_factory() as db:
        names = {c.id: c.name for c in db.query(Camera).all()}
    assert names == {"webcam-1": "Webcam 1", "video-analysis": "Video analysis"}


def test_start_rejects_unknown_sources(client: TestClient) -> None:
    bad = client.post("/api/v1/live/start", json={"source_type": "file", "source": "sample:x.mp4"})
    assert bad.status_code == 400
    traversal = client.post(
        "/api/v1/live/start", json={"source_type": "file", "source": "sample:../x.mp4"}
    )
    assert traversal.status_code == 400


def test_incident_list_carries_latest_review_label(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(Camera(id="cam", name="Cam"))
        incident = Incident(
            camera_id="cam",
            track_id="1",
            started_at=now,
            confirmed_at=now,
            detector_state="FALL_CONFIRMED",
            fall_score=0.9,
            model_name="m",
            model_version="1",
            config_version="c",
            evidence_features={},
        )
        db.add(incident)
        db.commit()
        incident_id = incident.id

    assert client.get("/api/v1/incidents").json()["items"][0]["review_label"] is None
    client.post(f"/api/v1/incidents/{incident_id}/reviews", json={"label": "confirmed_fall"})
    client.post(f"/api/v1/incidents/{incident_id}/reviews", json={"label": "non_fall"})
    assert client.get("/api/v1/incidents").json()["items"][0]["review_label"] == "non_fall"
    assert client.get(f"/api/v1/incidents/{incident_id}").json()["review_label"] == "non_fall"


def test_caregiver_cannot_upload_or_analyse_files(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    app = create_app(
        session_factory=session_factory,
        evidence_dir=tmp_path / "evidence",
        vlm_provider=None,
        upload_dir=tmp_path / "uploads",
        require_auth=True,
    )
    with TestClient(app) as client:
        client.post(
            "/api/v1/auth/signup",
            json={"full_name": "Ada Admin", "email": "ada@example.test", "password": "secure123"},
        )
        carer = {"full_name": "Casey Carer", "email": "casey@example.test", "password": "secure123"}
        client.post("/api/v1/auth/users", json=carer)
        client.post("/api/v1/auth/logout")
        client.post(
            "/api/v1/auth/login", json={"email": carer["email"], "password": carer["password"]}
        )
        video = {"file": ("kitchen.mp4", b"fake-video", "video/mp4")}
        assert client.post("/api/v1/live/uploads", files=video).status_code == 403
        assert client.delete("/api/v1/live/uploads/kitchen.mp4").status_code == 403
        started = client.post(
            "/api/v1/live/start", json={"source_type": "file", "source": "upload:kitchen.mp4"}
        )
        assert started.status_code == 403
        assert client.get("/api/v1/system/metrics").status_code == 403
        assert client.get("/api/v1/live/status").status_code == 200
