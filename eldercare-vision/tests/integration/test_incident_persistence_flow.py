"""End-to-end integration test for the complete Incident persistence lifecycle (P5-002)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eldercare.db.base import Base
from eldercare.incidents.schemas import IncidentFilter
from eldercare.incidents.service import IncidentService


class TestIncidentPersistenceFlow:
    """Integration test suite for the full database lifecycle flow."""

    def test_full_incident_persistence_and_query_flow(self) -> None:
        """Verify full lifecycle: camera auto-creation, incident record, evidence attachment,

        multi-stage human reviews, and complex filtering.
        """
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)

        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)
        camera_id = "cam-e2e-01"

        # 1. Record Fall Incident
        incident = service.record_fall_incident(
            camera_id=camera_id,
            track_id="trk-e2e-1",
            started_at=now,
            confirmed_at=now,
            fall_score=0.965,
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
        assert incident.camera_id == camera_id
        assert incident.fall_score == 0.965

        # 2. Attach Media Evidence (Snapshot + Video Clip)
        snap_id = str(uuid.uuid4())
        clip_id = str(uuid.uuid4())
        evidence_snap = service.attach_evidence(
            incident_id=incident.id,
            evidence_type="snapshot",
            storage_path=f"/evidence/{camera_id}/{snap_id}.jpg",
            mime_type="image/jpeg",
            sha256="d" * 64,
            captured_at=now,
            evidence_id=snap_id,
        )
        evidence_clip = service.attach_evidence(
            incident_id=incident.id,
            evidence_type="video_clip",
            storage_path=f"/evidence/{camera_id}/{clip_id}.mp4",
            mime_type="video/mp4",
            sha256="e" * 64,
            captured_at=now,
            evidence_id=clip_id,
        )
        assert evidence_snap.id == snap_id
        assert evidence_clip.id == clip_id

        # 3. Append Multi-stage Human Reviews
        rev1 = service.submit_review(
            incident_id=incident.id,
            label="uncertain",
            notes="Initial quick triage: needs verification",
            reviewer="triage_operator",
        )
        rev2 = service.submit_review(
            incident_id=incident.id,
            label="confirmed_fall",
            notes="Final verification: elder slipped on wet floor",
            reviewer="attending_physician",
        )
        assert rev1.label == "uncertain"
        assert rev2.label == "confirmed_fall"

        # 4. Record VLM Enrichment
        enrichment = service.record_enrichment(
            incident_id=incident.id,
            prompt_version="v1.0",
            status="completed",
            provider="gemini",
            model="gemini-1.5-pro",
            output={
                "fall_type": "forward_slip",
                "object_involved": "puddle",
                "immediate_posture": "prone",
            },
            duration_ms=480,
            completed_at=now,
        )
        assert enrichment.status == "completed"

        # 5. Fetch Full Incident with All Relations Eagerly Loaded
        full_incident = service.get_incident(incident.id, load_relations=True)
        assert full_incident.id == incident.id
        assert len(full_incident.evidence) == 2
        assert len(full_incident.reviews) == 2
        assert len(full_incident.enrichments) == 1

        # Assert Immutability of Detector Outputs
        assert full_incident.fall_score == 0.965
        assert full_incident.model_name == "yolo26s-pose.pt"
        assert full_incident.model_version == "1.0.0"
        assert full_incident.config_version == "1.0.0"
        assert full_incident.evidence_features["torso_angle"] == 18.4

        # 6. List and Filter Incidents
        filtered_list, count = service.list_incidents(
            IncidentFilter(
                camera_id=camera_id,
                review_label="confirmed_fall",
                limit=10,
            )
        )
        assert count == 1
        assert len(filtered_list) == 1
        assert filtered_list[0].id == incident.id

        Base.metadata.drop_all(engine)
