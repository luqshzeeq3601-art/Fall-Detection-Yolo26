"""Integration tests for async Agent/VLM enrichment, DB persistence, and events (P10-005)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eldercare.agents.client import MockVLMProvider, ProviderTimeoutError
from eldercare.agents.orchestrator import AgentEnrichmentOrchestrator
from eldercare.agents.privacy import EvidencePrivacyBoundary
from eldercare.agents.service import AsyncEnrichmentService
from eldercare.api.ws import ConnectionManager
from eldercare.db.base import Base
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.publisher import MqttPublisher


class InMemoryMqttTransport:
    """In-memory MQTT transport capture for integration testing."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retained: bool = False,
    ) -> None:
        self.published.append(
            {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retained": retained,
            }
        )


@pytest.fixture
def db_session_factory():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_full_agent_enrichment_success_flow(db_session_factory, tmp_path) -> None:
    incident_service = IncidentService(db_session_factory)
    now = datetime.now(timezone.utc)
    camera_id = "cam-living-room"

    # 1. Record incident in DB
    incident = incident_service.record_fall_incident(
        camera_id=camera_id,
        track_id="trk-100",
        started_at=now,
        confirmed_at=now,
        fall_score=0.92,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={
            "descent_velocity": 0.88,
            "aspect_ratio": 0.52,
            "torso_angle": 18.4,
        },
        auto_create_camera=True,
    )
    assert incident.id is not None

    # Setup valid snapshot on disk
    snapshot_file = tmp_path / "snap.jpg"
    snapshot_file.write_bytes(b"\xff\xd8\xff" + b"0" * 100)
    incident_service.attach_evidence(
        incident_id=incident.id,
        evidence_type="snapshot",
        storage_path=str(snapshot_file),
        mime_type="image/jpeg",
        sha256="a" * 64,
        captured_at=now,
    )

    # 2. Setup mock transports & managers
    mqtt_transport = InMemoryMqttTransport()
    mqtt_publisher = MqttPublisher(site_id="site-home", transport=mqtt_transport)
    mqtt_publisher.connect()

    ws_manager = ConnectionManager()
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()
    await ws_manager.connect(mock_ws)

    # 3. Setup VLM provider & orchestrator
    mock_provider = MockVLMProvider(
        provider_name="test-vlm-provider",
        model_name="test-model-v1",
        default_response={
            "schema_version": "1.0.0",
            "posture_description": "Elderly subject on rug near sofa",
            "apparent_motion_context": "Descent from standing to lying",
            "environmental_context": "Living room with rug and low coffee table",
            "scene_summary": "Subject resting on floor after fall",
            "confidence_assessment": "high",
            "uncertainty_factors": [],
            "postural_state": "lying_floor",
            "potential_hazards": ["Rug corner"],
        },
    )

    privacy_boundary = EvidencePrivacyBoundary(evidence_root=tmp_path)
    service = AsyncEnrichmentService(max_queue_size=10, max_concurrency=2)
    orchestrator = AgentEnrichmentOrchestrator(
        provider=mock_provider,
        service=service,
        incident_service=incident_service,
        privacy_boundary=privacy_boundary,
        mqtt_publisher=mqtt_publisher,
        ws_manager=ws_manager,
    )
    assert orchestrator.prompt_version == "v1.1.0"

    # 4. Start service and submit incident
    await service.start(num_workers=1)
    job = await service.submit_incident(incident_id=incident.id, camera_id=camera_id)
    assert job is not None

    # Wait briefly for worker execution
    await asyncio.sleep(0.15)
    await service.stop()

    # 5. Assert database persistence in agent_enrichments
    fresh_incident = incident_service.get_incident(incident.id, load_relations=True)
    assert len(fresh_incident.enrichments) == 1
    enrichment_row = fresh_incident.enrichments[0]
    assert enrichment_row.status == "completed"
    assert enrichment_row.provider == "test-vlm-provider"
    assert enrichment_row.model == "test-model-v1"
    assert enrichment_row.output["posture_description"] == "Elderly subject on rug near sofa"
    assert enrichment_row.duration_ms is not None

    # 6. Assert MQTT event published
    assert len(mqtt_transport.published) == 1
    pub_event = mqtt_transport.published[0]
    assert pub_event["topic"] == "eldercare/site-home/cam-living-room/agent"
    assert "agent.enrichment.completed" in pub_event["payload"]

    # 7. Assert WebSocket broadcast
    mock_ws.send_json.assert_called_once()
    ws_call_arg = mock_ws.send_json.call_args[0][0]
    assert ws_call_arg["event_type"] == "agent.enrichment.completed"
    assert ws_call_arg["incident_id"] == incident.id

    # 8. Assert core incident fall score and state remain unchanged
    assert fresh_incident.fall_score == 0.92
    assert fresh_incident.detector_state == "FALL_CONFIRMED"


@pytest.mark.asyncio
async def test_agent_enrichment_timeout_isolated_failure(db_session_factory) -> None:
    incident_service = IncidentService(db_session_factory)
    now = datetime.now(timezone.utc)
    camera_id = "cam-bedroom"

    incident = incident_service.record_fall_incident(
        camera_id=camera_id,
        track_id="trk-200",
        started_at=now,
        confirmed_at=now,
        fall_score=0.85,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={
            "descent_velocity": 0.75,
            "aspect_ratio": 0.48,
            "torso_angle": 12.0,
        },
        auto_create_camera=True,
    )

    mqtt_transport = InMemoryMqttTransport()
    mqtt_publisher = MqttPublisher(site_id="site-home", transport=mqtt_transport)
    mqtt_publisher.connect()

    mock_provider = MockVLMProvider(
        errors_to_raise=[ProviderTimeoutError("Simulated VLM timeout after 5.0s")]
    )

    service = AsyncEnrichmentService(max_queue_size=10, max_concurrency=1)
    orchestrator = AgentEnrichmentOrchestrator(
        provider=mock_provider,
        service=service,
        incident_service=incident_service,
        mqtt_publisher=mqtt_publisher,
    )
    assert orchestrator.prompt_version == "v1.1.0"

    await service.start(num_workers=1)
    await service.submit_incident(incident_id=incident.id, camera_id=camera_id)

    await asyncio.sleep(0.15)
    await service.stop()

    # Verify DB recorded timed_out status
    fresh_incident = incident_service.get_incident(incident.id, load_relations=True)
    assert len(fresh_incident.enrichments) == 1
    enrichment_row = fresh_incident.enrichments[0]
    assert enrichment_row.status == "timed_out"
    assert enrichment_row.error_code == "TIMEOUT"

    # Verify MQTT failure event
    assert len(mqtt_transport.published) == 1
    assert "agent.enrichment.failed" in mqtt_transport.published[0]["payload"]

    # Invariance check: incident fall_score untouched
    assert fresh_incident.fall_score == 0.85


@pytest.mark.asyncio
async def test_agent_enrichment_schema_rejection_isolated_failure(db_session_factory) -> None:
    incident_service = IncidentService(db_session_factory)
    now = datetime.now(timezone.utc)
    camera_id = "cam-hallway"

    incident = incident_service.record_fall_incident(
        camera_id=camera_id,
        track_id="trk-300",
        started_at=now,
        confirmed_at=now,
        fall_score=0.90,
        model_name="yolo26s-pose.pt",
        model_version="1.0.0",
        config_version="1.0.0",
        evidence_features={"descent_velocity": 0.80},
        auto_create_camera=True,
    )

    # Provider returning invalid schema (missing required fields)
    mock_provider = MockVLMProvider(
        default_response={"schema_version": "1.0.0", "invalid_key": "bad_value"}
    )

    service = AsyncEnrichmentService(max_queue_size=10, max_concurrency=1)
    orchestrator = AgentEnrichmentOrchestrator(
        provider=mock_provider,
        service=service,
        incident_service=incident_service,
    )
    assert orchestrator.prompt_version == "v1.1.0"

    await service.start(num_workers=1)
    await service.submit_incident(incident_id=incident.id, camera_id=camera_id)

    await asyncio.sleep(0.15)
    await service.stop()

    fresh_incident = incident_service.get_incident(incident.id, load_relations=True)
    assert len(fresh_incident.enrichments) == 1
    enrichment_row = fresh_incident.enrichments[0]
    assert enrichment_row.status == "failed"
    assert enrichment_row.error_code == "PROVIDERMALFORMEDRESPONSEERROR"
    assert fresh_incident.fall_score == 0.90
