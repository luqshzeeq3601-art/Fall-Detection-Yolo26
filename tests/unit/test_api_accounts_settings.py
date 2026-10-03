"""Accounts, auth gating, workspace settings, incident stats/search/export, and source safety."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.api.auth import hash_password, verify_password
from eldercare.db.base import Base
from eldercare.db.models import Camera, Incident, IncidentEvidence
from eldercare.evidence.storage import EvidenceStorage
from eldercare.incidents.retention import purge_expired_incidents
from eldercare.live.sources import SourceCatalog, SourceError

ACCOUNT = {"full_name": "Ada Operator", "email": "Ada@Example.test", "password": "secure123"}


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


def _incident(camera_id: str, confirmed: datetime, track: str = "1") -> Incident:
    return Incident(
        camera_id=camera_id,
        track_id=track,
        started_at=confirmed,
        confirmed_at=confirmed,
        detector_state="FALL_CONFIRMED",
        fall_score=0.9,
        model_name="v6_3_phase3b",
        model_version="6.3",
        config_version="test",
        evidence_features={},
    )


def test_password_hash_roundtrip() -> None:
    stored = hash_password("secure123")
    assert stored.startswith("scrypt$") and "secure123" not in stored
    assert verify_password("secure123", stored)
    assert not verify_password("secure124", stored)
    assert not verify_password("secure123", "garbage")


def test_data_routes_require_sign_in(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    for path in (
        "/api/v1/cameras",
        "/api/v1/incidents",
        "/api/v1/settings",
        "/api/v1/system/status",
    ):
        assert client.get(path).status_code == 401


def test_signup_login_logout_flow(client: TestClient) -> None:
    created = client.post("/api/v1/auth/signup", json=ACCOUNT)
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "ada@example.test"
    assert body["role"] == "admin"  # first account
    assert "password" not in created.text.lower()
    assert client.get("/api/v1/cameras").status_code == 200

    # The same email cannot register twice.
    assert client.post("/api/v1/auth/signup", json=ACCOUNT).status_code == 409
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/cameras").status_code == 401

    bad = client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": "nope1234"}
    )
    assert bad.status_code == 401
    good = client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
    )
    assert good.status_code == 200
    assert client.get("/api/v1/auth/me").json()["full_name"] == "Ada Operator"


def test_signup_rejects_weak_password(client: TestClient) -> None:
    res = client.post("/api/v1/auth/signup", json={**ACCOUNT, "password": "lettersonly"})
    assert res.status_code == 422


def test_password_change(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=ACCOUNT)
    wrong = client.post(
        "/api/v1/auth/password", json={"current_password": "x1234567", "new_password": "newpass99"}
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/v1/auth/password",
        json={"current_password": ACCOUNT["password"], "new_password": "newpass99"},
    )
    assert ok.status_code == 204
    client.post("/api/v1/auth/logout")
    login = client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": "newpass99"}
    )
    assert login.status_code == 200


def test_settings_roundtrip_and_validation(client: TestClient) -> None:
    client.post("/api/v1/auth/signup", json=ACCOUNT)
    current = client.get("/api/v1/settings").json()["settings"]
    assert current["fall_threshold"] is None and current["retention_days"] is None
    updated = {**current, "fall_threshold": 0.6, "blur_faces": True, "retention_days": 30}
    assert client.put("/api/v1/settings", json=updated).status_code == 200
    assert client.get("/api/v1/settings").json()["settings"] == updated
    assert (
        client.put("/api/v1/settings", json={**updated, "fall_threshold": 0.95}).status_code == 422
    )


def test_stats_search_reviewed_and_export(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    client.post("/api/v1/auth/signup", json=ACCOUNT)
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(Camera(id="cam-living", name="Living room"))
        db.add(Camera(id="cam-hall", name="Hallway"))
        recent = _incident("cam-living", now - timedelta(minutes=5))
        older = _incident("cam-hall", now - timedelta(days=3), track="7")
        db.add_all([recent, older])
        db.commit()
        recent_id = recent.id

    review = client.post(f"/api/v1/incidents/{recent_id}/reviews", json={"label": "confirmed_fall"})
    assert review.status_code == 201
    assert review.json()["reviewer"] == "Ada Operator"

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stats = client.get(
        "/api/v1/incidents/stats", params={"day_start": day_start.isoformat()}
    ).json()
    assert stats["total"] == 2
    assert stats["reviewed"] == 1 and stats["unreviewed"] == 1
    assert stats["confirmed_falls"] == 1
    assert len(stats["last_7_days"]) == 7 and sum(d["count"] for d in stats["last_7_days"]) == 2

    by_name = client.get("/api/v1/incidents", params={"q": "living"}).json()
    assert [i["id"] for i in by_name["items"]] == [recent_id]
    assert client.get("/api/v1/incidents", params={"q": "%"}).json()["total"] == 0
    assert client.get("/api/v1/incidents", params={"reviewed": "true"}).json()["total"] == 1
    assert client.get("/api/v1/incidents", params={"reviewed": "false"}).json()["total"] == 1

    export = client.get("/api/v1/incidents/export.jsonl", params={"ids": [recent_id]})
    assert export.status_code == 200
    assert export.headers["x-record-count"] == "1"
    assert recent_id in export.text


def test_source_catalog_rejects_traversal(tmp_path: Path) -> None:
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "clip.mp4").write_bytes(b"0")
    catalog = SourceCatalog(upload_dir=tmp_path / "uploads", sample_dir=samples)
    assert catalog.resolve("file", "sample:clip.mp4").path == samples / "clip.mp4"
    assert catalog.resolve("webcam", "0").webcam_index == 0
    for source_type, source in [
        ("file", "sample:../secret.mp4"),
        ("file", "upload:clip.exe"),
        ("file", "/etc/passwd"),
        ("webcam", "rtsp://cam"),
        ("webcam", "42"),
    ]:
        with pytest.raises(SourceError):
            catalog.resolve(source_type, source)


def test_retention_purges_old_incidents_and_files(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    storage = EvidenceStorage(base_dir=tmp_path / "evidence")
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(Camera(id="cam", name="Cam"))
        old = _incident("cam", now - timedelta(days=10))
        fresh = _incident("cam", now - timedelta(hours=1))
        db.add_all([old, fresh])
        db.flush()
        rel = storage.save_file("old/keyframe.jpg", b"jpeg")
        db.add(
            IncidentEvidence(
                incident_id=old.id,
                evidence_type="snapshot",
                storage_path=rel[0],
                mime_type="image/jpeg",
                sha256="0" * 64,
                captured_at=now,
            )
        )
        db.commit()
        fresh_id = fresh.id

    assert purge_expired_incidents(session_factory, storage, retention_days=7) == 1
    with session_factory() as db:
        assert [i.id for i in db.query(Incident).all()] == [fresh_id]
    assert not storage.exists("old/keyframe.jpg")


def test_login_rate_limiting_after_consecutive_failures(client: TestClient) -> None:
    from eldercare.api.routers.auth import login_rate_limiter

    victim = {"full_name": "Victim User", "email": "victim@example.test", "password": "secure123"}
    client.post("/api/v1/auth/signup", json=victim)
    client.post("/api/v1/auth/logout")

    try:
        # 5 failed login attempts
        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": victim["email"], "password": "wrongpassword1"},
            )
            assert resp.status_code == 401

        # 6th attempt must be blocked with 429
        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": victim["email"], "password": "wrongpassword1"},
        )
        assert blocked.status_code == 429
        assert "Too many failed login attempts" in blocked.json()["error"]["message"]
        assert "retry-after" in blocked.headers or "Retry-After" in blocked.headers
    finally:
        with login_rate_limiter._lock:
            login_rate_limiter._failures.clear()


def test_non_admin_cannot_modify_settings_or_delete_cameras(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # First user is admin
    client.post("/api/v1/auth/signup", json=ACCOUNT)
    # Second user is a regular operator, created by the admin
    op_account = {"full_name": "Bob Operator", "email": "bob@example.test", "password": "secure123"}
    created_op = client.post("/api/v1/auth/users", json=op_account)
    assert created_op.status_code == 201
    assert created_op.json()["role"] == "operator"
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login", json={"email": op_account["email"], "password": op_account["password"]}
    ).status_code == 200

    # Seed a camera
    with session_factory() as db:
        db.add(Camera(id="cam-rbac", name="RBAC Test Cam"))
        db.commit()

    # Operator Bob tries to update settings -> 403 Forbidden
    resp = client.put("/api/v1/settings", json={"fall_threshold": 0.5})
    assert resp.status_code == 403
    assert "Admin role required" in resp.json()["error"]["message"]

    # Operator Bob tries to delete camera -> 403 Forbidden
    del_resp = client.delete("/api/v1/cameras/cam-rbac")
    assert del_resp.status_code == 403
    assert "Admin role required" in del_resp.json()["error"]["message"]

    # Switch back to admin Ada
    client.post("/api/v1/auth/logout")
    login_admin = client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
    )
    assert login_admin.status_code == 200

    # Admin Ada can modify settings and delete camera
    admin_put = client.put("/api/v1/settings", json={"fall_threshold": 0.5})
    assert admin_put.status_code == 200
    admin_del = client.delete("/api/v1/cameras/cam-rbac")
    assert admin_del.status_code == 204


def test_cookie_secure_on_https_request(client: TestClient) -> None:
    res = client.post(
        "/api/v1/auth/signup",
        json={"full_name": "Carol Safe", "email": "carol@example.test", "password": "secure123"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert res.status_code == 201
    cookie_header = res.headers.get("set-cookie", "").lower()
    assert "secure" in cookie_header
    assert "httponly" in cookie_header


def test_setup_status_one_time_admin_then_caregiver_signup(client: TestClient) -> None:
    assert client.get("/api/v1/auth/setup-status").json() == {"needs_setup": True}
    first = client.post(
        "/api/v1/auth/signup", json={**ACCOUNT, "job_role": "caregiver"}
    )
    assert first.status_code == 201
    assert first.json()["role"] == "admin"
    assert first.json()["job_role"] == "facility-admin"
    client.post("/api/v1/auth/logout")

    assert client.get("/api/v1/auth/setup-status").json() == {"needs_setup": False}
    other = {
        "full_name": "Mallory X",
        "email": "mallory@example.test",
        "password": "secure123",
        "job_role": "facility-admin",
    }
    later = client.post("/api/v1/auth/signup", json=other)
    assert later.status_code == 201
    assert later.json()["role"] == "operator"
    assert later.json()["job_role"] == "caregiver"
    assert client.get("/api/v1/auth/setup-status").json() == {"needs_setup": False}


def test_admin_manages_team_members(client: TestClient) -> None:
    admin_id = client.post("/api/v1/auth/signup", json=ACCOUNT).json()["id"]
    bob = {"full_name": "Bob Carer", "email": "bob@example.test", "password": "secure123"}
    bob_id = client.post("/api/v1/auth/users", json=bob).json()["id"]

    # Admin cannot change or remove themself, and the last admin cannot be demoted.
    assert (
        client.patch(f"/api/v1/auth/users/{admin_id}", json={"role": "operator"}).status_code == 400
    )
    assert client.delete(f"/api/v1/auth/users/{admin_id}").status_code == 400
    assert (
        client.patch(f"/api/v1/auth/users/{bob_id}", json={"new_password": "short"}).status_code
        == 422
    )

    promoted = client.patch(f"/api/v1/auth/users/{bob_id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["job_role"] == "facility-admin"
    reset = client.patch(
        f"/api/v1/auth/users/{bob_id}", json={"role": "operator", "new_password": "newpass99"}
    )
    assert reset.json()["role"] == "operator"

    client.post("/api/v1/auth/logout")
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": bob["email"], "password": "newpass99"}
        ).status_code
        == 200
    )
    # A caregiver cannot manage the team.
    assert client.delete(f"/api/v1/auth/users/{admin_id}").status_code == 403
    assert (
        client.patch(f"/api/v1/auth/users/{admin_id}", json={"role": "operator"}).status_code == 403
    )

    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/login", json={"email": ACCOUNT["email"], "password": ACCOUNT["password"]}
    )
    assert client.delete(f"/api/v1/auth/users/{bob_id}").status_code == 204
    assert client.delete(f"/api/v1/auth/users/{bob_id}").status_code == 404
    assert [u["id"] for u in client.get("/api/v1/auth/users").json()] == [admin_id]


def test_caregiver_cannot_use_admin_tools(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin_id = client.post("/api/v1/auth/signup", json=ACCOUNT).json()["id"]
    carer = {"full_name": "Casey Carer", "email": "casey@example.test", "password": "secure123"}
    client.post("/api/v1/auth/users", json=carer)
    with session_factory() as db:
        db.add(Camera(id="cam-x", name="Hall"))
        db.commit()
    assert client.get("/api/v1/incidents/export.jsonl").status_code == 200

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": carer["email"], "password": carer["password"]})
    assert client.get("/api/v1/incidents/export.jsonl").status_code == 403
    assert client.patch("/api/v1/cameras/cam-x", json={"name": "Lounge"}).status_code == 403
    assert client.post("/api/v1/cameras", json={"id": "cam-y", "name": "New"}).status_code == 403

    team = {member["id"]: member for member in client.get("/api/v1/auth/users").json()}
    assert team[admin_id]["email"] is None
    assert any(m["email"] == carer["email"] for m in team.values())  # their own address stays visible
