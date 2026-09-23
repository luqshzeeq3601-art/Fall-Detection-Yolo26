"""Failure/security intersection regression tests (P8-003).

Fresh attack-surface drills over real components: injection strings through
reviews/filters, API traversal battery, hostile WebSocket frames, MQTT
envelope fuzz, payload depth bombs, tracked-source secret scan, and crash
envelope redaction. Deterministic; no network, broker, GPU, or cameras.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.api.ws import ConnectionManager
from eldercare.db.base import Base
from eldercare.incidents.schemas import IncidentFilter
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.publisher import MqttPublisher
from eldercare.mqtt.resilience import publish_best_effort

REPO_ROOT = Path(__file__).resolve().parents[3]

_NASTY = [
    "' OR '1'='1",
    "'; DROP TABLE incidents; --",
    "../../etc/passwd",
    "..\\..\\windows\\system32",
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "{{7*7}}",
    "${jndi:ldap://evil/x}",
    "\x00",
    "A" * 5000,
]


def _memory_service() -> IncidentService:
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return IncidentService(sessionmaker(bind=engine, expire_on_commit=False))


def test_injection_strings_stored_inert_and_tables_intact() -> None:
    """Hostile review/filter input is stored as inert text; schema survives."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = IncidentService(sessionmaker(bind=engine, expire_on_commit=False))
    now = datetime.now(timezone.utc)
    incident = service.record_fall_incident(
        camera_id="cam-sec-01",
        track_id="1",
        started_at=now,
        confirmed_at=now,
        fall_score=0.8,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={},
        auto_create_camera=True,
    )
    for nasty in _NASTY:
        service.submit_review(incident_id=incident.id, label="uncertain", notes=nasty[:1500])
    reviews = service.get_incident(incident.id).reviews
    assert len(reviews) == len(_NASTY)
    assert reviews[0].notes == _NASTY[0]
    with pytest.raises(Exception, match="2000|too_long|max_length"):
        service.submit_review(incident_id=incident.id, label="uncertain", notes="A" * 5000)
    items, total = service.list_incidents(IncidentFilter(camera_id="' OR '1'='1"))
    assert total == 0
    assert items == []
    with engine.connect() as connection:
        count = connection.execute(text("SELECT COUNT(*) FROM incidents")).scalar()
    assert count == 1


def test_api_traversal_battery_rejected() -> None:
    """Traversal/absolute/encoded evidence paths stay contained via the API."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=factory)
    client = TestClient(app, raise_server_exceptions=False)
    # NOTE: literal ".." segments are normalized client-side by HTTP and never
    # reach the app as traversal; the battery below covers values the server
    # actually receives. For every response: no evidence served, no traceback.
    for evil in (
        "/etc/passwd",
        "%2e%2e/%2e%2e/x",
        "....//....//x",
        "valid-id/%2e%2e",
        "..%2f..%2fsecret",
    ):
        response = client.get(f"/incidents/does-not-exist/evidence/{evil}")
        assert response.status_code in (400, 404, 422), evil
        assert "X-Evidence-SHA256" not in response.headers
        assert "Traceback" not in response.text


def test_websocket_hostile_frames_dont_break_broker() -> None:
    """Binary/garbage client frames end only that connection, pruned cleanly."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=factory)
    client = TestClient(app, raise_server_exceptions=False)
    manager: ConnectionManager = app.state.connection_manager
    with client.websocket_connect("/ws/events") as good:
        good.send_text("ping")
        assert good.receive_text() == "pong"
        with client.websocket_connect("/ws/events") as hostile:
            hostile.send_bytes(b"\xff\xfe\x00binary")
        deadline = time.monotonic() + 2.0
        while manager.active_count != 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert manager.active_count == 1
        good.send_text("ping")
        assert good.receive_text() == "pong"
    assert manager.active_count == 0


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "null",
        "[]",
        "[1,2]",
        '{"event_id": 1}',
        '{"event_id":"a","event_type":"t","schema_version":"1.0","occurred_at":"x","source":"s"}',
        '{"event_id":"a","event_type":"t","schema_version":"1.0","occurred_at":123,"source":"s"}',
        '{"event_id":"a","event_type":"t","schema_version":"1.0","occurred_at":"2026-09-23T12:00:00Z","source":"s","payload":[]}',
        '{"event_id":"' + "A" * 100000 + '"}',
        '{"a":' * 50000,
    ],
    ids=[
        "empty",
        "null",
        "array",
        "int-array",
        "numeric-id",
        "bad-date",
        "numeric-date",
        "non-object-payload",
        "huge-string",
        "truncated-deep",
    ],
)
def test_mqtt_envelope_fuzz_never_escapes_as_other_errors(raw: str) -> None:
    """Malformed envelopes fail closed as ValueError or parse safely."""
    try:
        event = MqttEvent.from_json(raw)
    except ValueError:
        return
    assert isinstance(event.event_id, str) and event.event_id


def test_payload_depth_bomb_fails_closed_with_value_error() -> None:
    """SEC-001 regression: extreme nesting → ValueError, never RecursionError."""
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="s", transport=transport)
    publisher.connect()
    deep: dict = {}
    current = deep
    for _ in range(40):
        current["a"] = {}
        current = current["a"]
    event = MqttEvent.create(event_type="fall.confirmed", camera_id="c", payload=deep)
    with pytest.raises(ValueError):
        publisher.publish_event(event, "events/fall")
    outcome = publish_best_effort(publisher, event, "events/fall")
    assert outcome.delivered is False


def test_list_nested_sensitive_key_rejected() -> None:
    """SEC-001 companion: sensitive keys inside lists are caught too."""
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="s", transport=transport)
    publisher.connect()
    event = MqttEvent.create(
        event_type="fall.confirmed", camera_id="c", payload={"items": [{"password": "x"}]}
    )
    with pytest.raises(ValueError):
        publisher.publish_event(event, "events/fall")


def test_tracked_sources_carry_no_credential_material() -> None:
    """Committed src/deployment/compose carry no passwords, keys, or RTSP userinfo."""
    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "eldercare-vision/src",
            "eldercare-vision/deployment",
            "eldercare-vision/docker-compose.yml",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout.split()
    assert tracked, "expected tracked source files"
    suspicious: list[str] = []
    placeholders = (
        "user:pass",
        "user:",
        "pass@",
        "<",
        ">",
        "...",
        "\u2026",
        "example",
        "changeme",
        "dummy",
        "test",
        "your-",
        "localhost",
    )
    for path in tracked:
        full = REPO_ROOT / path
        try:
            with open(full, encoding="utf-8", errors="strict") as handle:
                text_body = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text_body.splitlines(), 1):
            lowered = line.lower()
            if "rtsp://" in lowered and "@" in line:
                if any(token in lowered for token in placeholders):
                    continue
                suspicious.append(f"{path}:{lineno}: rtsp userinfo")
            if "begin " in lowered and "private key" in lowered:
                suspicious.append(f"{path}:{lineno}: private key")
    assert suspicious == []


crash_router = APIRouter()


@crash_router.get("/test/crash")
def _crash() -> None:
    raise RuntimeError("Simulated DB credential failure: pwd=supersecret")


def test_crash_envelope_suppresses_internals() -> None:
    """Unhandled crash → generic 500 envelope; internals never leak."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app(session_factory=factory)
    app.include_router(crash_router)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/test/crash")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "supersecret" not in response.text
    assert "Traceback" not in response.text
