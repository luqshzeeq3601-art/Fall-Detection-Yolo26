"""Integration test: fall event -> incident + keyframes -> async VLM -> review queue."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.agents.orchestrator import AgentEnrichmentOrchestrator
from eldercare.agents.privacy import EvidencePrivacyBoundary
from eldercare.agents.service import AsyncEnrichmentService
from eldercare.db.base import Base
from eldercare.evidence.storage import EvidenceStorage
from eldercare.fall_engine.state_machine.states import FallEvent
from eldercare.incidents.bridge import FallIncidentBridge
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import IncidentFilter
from eldercare.incidents.service import IncidentService


class _ScriptedVLM:
    """Returns a fall verdict per camera so the test controls which incident is flagged."""

    provider_name = "scripted-vlm"
    model_name = "scripted-v1"

    def __init__(self, verdicts: dict[str, str]) -> None:
        self._verdicts = verdicts
        self.media_paths: list[str | None] = []

    async def generate_enrichment(
        self,
        prompt: str,
        media_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.media_paths.append(media_path)
        camera_id = (context or {})["camera_id"]
        return {
            "schema_version": "1.1.0",
            "posture_description": "Person low to the ground",
            "environmental_context": "Indoor room",
            "scene_summary": "Person near floor",
            "confidence_assessment": "medium",
            "fall_assessment": self._verdicts[camera_id],
        }


def _event(camera_id: str, track_id: int) -> FallEvent:
    now = time.time()
    return FallEvent(
        camera_id=camera_id,
        track_id=track_id,
        confirmed_timestamp=now,
        candidate_timestamp=now - 2.0,
        down_start_timestamp=now - 1.0,
        features=None,  # type: ignore[arg-type]
        confidence=0.91,
    )


async def _wait_for_enrichments(service: IncidentService, ids: list[str]) -> None:
    for _ in range(100):
        if all(service.get_incident(i, load_relations=True).enrichments for i in ids):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("enrichment did not complete in time")


@pytest.mark.asyncio
async def test_bridge_persists_incident_and_flags_vlm_disagreement(
    tmp_path: Path,
) -> None:
    # StaticPool: the bridge runs in a worker thread and must see the same in-memory DB.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    incident_service = IncidentService(session_factory)
    storage = EvidenceStorage(base_dir=tmp_path / "evidence")

    provider = _ScriptedVLM({"cam-agree": "fall", "cam-disagree": "no_fall"})
    enrichment_service = AsyncEnrichmentService(max_queue_size=10, max_concurrency=2)
    AgentEnrichmentOrchestrator(
        provider=provider,
        service=enrichment_service,
        incident_service=incident_service,
        privacy_boundary=EvidencePrivacyBoundary(evidence_root=storage.base_dir),
    )
    await enrichment_service.start(num_workers=1)

    bridge = FallIncidentBridge(
        incident_service=incident_service,
        evidence_storage=storage,
        model_name="v6_3_phase3b",
        model_version="6.3",
        config_version="test",
        enrichment_service=enrichment_service,
        enrichment_loop=asyncio.get_running_loop(),
    )
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    try:
        # The detection loop is synchronous and runs off the event loop thread.
        agree = await asyncio.to_thread(
            bridge.handle_fall_event, _event("cam-agree", 1), [frame, frame]
        )
        disagree = await asyncio.to_thread(
            bridge.handle_fall_event, _event("cam-disagree", 2), [frame]
        )
        await _wait_for_enrichments(incident_service, [agree.id, disagree.id])
    finally:
        await enrichment_service.stop()

    # Incident + evidence persisted; detector output untouched by the VLM.
    stored = incident_service.get_incident(agree.id, load_relations=True)
    assert stored.fall_score == pytest.approx(0.91)
    assert stored.track_id == "1"
    assert sorted(e.storage_path for e in stored.evidence) == [
        f"cam-agree/{agree.id}/keyframe_00.jpg",
        f"cam-agree/{agree.id}/keyframe_01.jpg",
    ]
    assert stored.enrichments[0].status == "completed"
    assert stored.enrichments[0].output["fall_assessment"] == "fall"
    # The VLM received keyframe_00 through the privacy boundary.
    assert any(p and p.endswith("keyframe_00.jpg") for p in provider.media_paths)

    # Only the incident the VLM disputed lands in the review queue.
    with session_factory() as session:
        flagged, total = IncidentRepository(session).list_incidents(
            IncidentFilter(needs_review=True)
        )
    assert total == 1
    assert [i.id for i in flagged] == [disagree.id]

    # A human review clears it from the queue.
    incident_service.submit_review(disagree.id, label="non_fall", reviewer="nurse-1")
    with session_factory() as session:
        _, total_after = IncidentRepository(session).list_incidents(
            IncidentFilter(needs_review=True)
        )
    assert total_after == 0


def test_bridge_without_enrichment_still_records_incident(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    incident_service = IncidentService(
        sessionmaker(bind=engine, expire_on_commit=False)
    )
    bridge = FallIncidentBridge(
        incident_service=incident_service,
        evidence_storage=EvidenceStorage(base_dir=tmp_path),
        model_name="v6_3_phase3b",
        model_version="6.3",
        config_version="test",
    )
    bad_frame = np.zeros(
        (10, 10), dtype=np.uint8
    )  # wrong shape: evidence skipped, not fatal

    incident = bridge.handle_fall_event(_event("cam-x", 7), [bad_frame])

    stored = incident_service.get_incident(incident.id, load_relations=True)
    assert stored.evidence == []
    assert stored.enrichments == []


def test_bridge_requires_service_and_loop_together(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FallIncidentBridge(
            incident_service=None,  # type: ignore[arg-type]
            evidence_storage=EvidenceStorage(base_dir=tmp_path),
            model_name="m",
            model_version="v",
            config_version="c",
            enrichment_service=AsyncEnrichmentService(),
        )
