"""Unit and integration tests for WebSocket event streaming (P5-007)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.api.app import create_app
from eldercare.api.schemas import WebSocketEvent
from eldercare.api.ws import ConnectionManager
from eldercare.db.models import Base
from eldercare.evidence.storage import EvidenceStorage


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
def connection_manager() -> ConnectionManager:
    """Provide a fresh ConnectionManager instance."""
    return ConnectionManager()


@pytest.fixture
def client(
    test_db_session_factory: sessionmaker[Session],
    connection_manager: ConnectionManager,
    tmp_path,
) -> TestClient:
    """Provide FastAPI test client configured with in-memory DB and test connection manager."""
    evidence_storage = EvidenceStorage(base_dir=tmp_path / "evidence_store")
    app = create_app(
        session_factory=test_db_session_factory,
        evidence_storage=evidence_storage,
        connection_manager=connection_manager,
    )
    return TestClient(app)


def test_websocket_event_schema_validation() -> None:
    """Verify WebSocketEvent serialization, field generation, and extra field rejection."""
    t_now = datetime(2026, 9, 23, 17, 0, 0, tzinfo=timezone.utc)
    evt = WebSocketEvent(
        event_type="fall.confirmed",
        occurred_at=t_now,
        camera_id="cam-01",
        incident_id="inc-999",
        payload={"score": 0.98, "track_id": "tr-5"},
    )
    dumped = evt.model_dump(mode="json")
    assert dumped["event_type"] == "fall.confirmed"
    assert dumped["camera_id"] == "cam-01"
    assert dumped["incident_id"] == "inc-999"
    assert dumped["payload"]["score"] == 0.98
    assert "event_id" in dumped
    assert len(dumped["event_id"]) == 36

    # Test extra field forbidden
    with pytest.raises(ValueError):
        WebSocketEvent(
            event_type="fall.started",
            unknown_injection="malicious",  # type: ignore[call-arg]
        )


def test_websocket_connect_and_receive_broadcast(
    client: TestClient,
    connection_manager: ConnectionManager,
) -> None:
    """Verify connecting to /ws/events and receiving broadcast events."""
    with client.websocket_connect("/ws/events") as ws:
        assert connection_manager.active_count == 1

        # Broadcast event
        evt = WebSocketEvent(
            event_type="fall.confirmed",
            camera_id="cam-01",
            incident_id="inc-101",
            payload={"fall_score": 0.96},
        )
        asyncio.run(connection_manager.broadcast(evt))

        # Receive on client
        msg = ws.receive_json()
        assert msg["event_type"] == "fall.confirmed"
        assert msg["camera_id"] == "cam-01"
        assert msg["incident_id"] == "inc-101"
        assert msg["payload"]["fall_score"] == 0.96
        assert "event_id" in msg
        assert "occurred_at" in msg

    # Disconnect cleans up
    assert connection_manager.active_count == 0


def test_websocket_multiple_clients_broadcast(
    client: TestClient,
    connection_manager: ConnectionManager,
) -> None:
    """Verify all connected clients receive broadcasted events concurrently."""
    with client.websocket_connect("/ws/events") as ws1:
        with client.websocket_connect("/ws/events") as ws2:
            assert connection_manager.active_count == 2

            evt = WebSocketEvent(
                event_type="camera.status",
                camera_id="cam-02",
                payload={"status": "online"},
            )
            delivered = asyncio.run(connection_manager.broadcast(evt))
            assert delivered == 2

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["event_type"] == "camera.status"
            assert msg2["event_type"] == "camera.status"
            assert msg1["camera_id"] == "cam-02"
            assert msg2["camera_id"] == "cam-02"

    assert connection_manager.active_count == 0


def test_websocket_keepalive_ping_pong(client: TestClient) -> None:
    """Verify WebSocket client can send ping and receive pong."""
    with client.websocket_connect("/ws/events") as ws:
        ws.send_text("ping")
        resp = ws.receive_text()
        assert resp == "pong"


def test_websocket_api_v1_prefix(
    client: TestClient,
    connection_manager: ConnectionManager,
) -> None:
    """Verify WebSocket route is accessible at /api/v1/ws/events."""
    with client.websocket_connect("/api/v1/ws/events") as ws:
        assert connection_manager.active_count == 1
        evt = WebSocketEvent(event_type="system.heartbeat", payload={"fps": 30.0})
        asyncio.run(connection_manager.broadcast(evt))
        msg = ws.receive_json()
        assert msg["event_type"] == "system.heartbeat"
        assert msg["payload"]["fps"] == 30.0


@pytest.mark.asyncio
async def test_websocket_dead_connection_pruning() -> None:
    """Verify broken sockets are pruned during broadcast without raising exceptions."""
    manager = ConnectionManager()

    good_ws = AsyncMock()
    bad_ws = AsyncMock()
    bad_ws.send_json.side_effect = RuntimeError("Socket broken")

    # Manually register mocks
    manager._active_connections.add(good_ws)
    manager._active_connections.add(bad_ws)
    assert manager.active_count == 2

    evt = WebSocketEvent(event_type="fall.ended", camera_id="cam-01")
    sent = await manager.broadcast(evt)

    assert sent == 1
    assert manager.active_count == 1
    assert good_ws in manager._active_connections
    assert bad_ws not in manager._active_connections
