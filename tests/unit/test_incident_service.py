"""Unit tests for IncidentService (P5-002)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eldercare.db.base import Base
from eldercare.incidents.schemas import (
    CameraNotFoundError,
    IncidentFilter,
    IncidentNotFoundError,
    InvalidReviewLabelError,
)
from eldercare.incidents.service import IncidentService


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    """Create in-memory SQLite engine and sessionmaker."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)


class TestIncidentService:
    """Test suite verifying transactional service layer behavior."""

    def test_record_fall_incident_auto_provisions_camera(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Verify recording an incident automatically creates the camera entity."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        incident = service.record_fall_incident(
            camera_id="cam-auto-1",
            track_id="trk-10",
            started_at=now,
            confirmed_at=now,
            fall_score=0.94,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"angle": 12.5},
            auto_create_camera=True,
        )

        assert incident.id is not None
        assert incident.camera_id == "cam-auto-1"
        assert incident.fall_score == 0.94

        # Query back via service
        retrieved = service.get_incident(incident.id)
        assert retrieved.id == incident.id
        assert retrieved.camera_id == "cam-auto-1"

    def test_record_fall_incident_without_auto_camera_raises(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Verify CameraNotFoundError when auto_create_camera=False and camera absent."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        with pytest.raises(CameraNotFoundError):
            service.record_fall_incident(
                camera_id="cam-nonexistent",
                track_id="trk-10",
                started_at=now,
                confirmed_at=now,
                fall_score=0.94,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
                auto_create_camera=False,
            )

    def test_submit_review_validation_and_append_only(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Verify human review validation and append-only ledger functionality."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        incident = service.record_fall_incident(
            camera_id="cam-review-test",
            track_id="trk-20",
            started_at=now,
            confirmed_at=now,
            fall_score=0.89,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"descent_velocity": 0.77},
        )

        # 1. Invalid label should raise InvalidReviewLabelError
        with pytest.raises(InvalidReviewLabelError):
            service.submit_review(
                incident_id=incident.id,
                label="invalid_label_123",
                notes="Bad label test",
            )

        # 2. Valid reviews should append
        r1 = service.submit_review(
            incident_id=incident.id,
            label="uncertain",
            notes="Need second opinion",
            reviewer="nurse_mary",
        )
        assert r1.label == "uncertain"
        assert r1.reviewer == "nurse_mary"

        r2 = service.submit_review(
            incident_id=incident.id,
            label="confirmed_fall",
            notes="Confirmed upon video review",
            reviewer="dr_smith",
        )
        assert r2.label == "confirmed_fall"
        assert r2.reviewer == "dr_smith"

        # 3. Verify incident detector outputs remain completely untouched
        refetched = service.get_incident(incident.id)
        assert refetched.fall_score == 0.89
        assert refetched.model_name == "yolo26s-pose.pt"
        assert len(refetched.reviews) == 2
        assert refetched.reviews[0].label == "uncertain"
        assert refetched.reviews[1].label == "confirmed_fall"

    def test_attach_evidence_and_enrichment(self, session_factory: sessionmaker[Session]) -> None:
        """Verify attaching media evidence and recording agent enrichments."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        incident = service.record_fall_incident(
            camera_id="cam-ev-test",
            track_id="trk-30",
            started_at=now,
            confirmed_at=now,
            fall_score=0.91,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={},
        )

        ev = service.attach_evidence(
            incident_id=incident.id,
            evidence_type="snapshot",
            storage_path="/data/evidence/test_snap.jpg",
            mime_type="image/jpeg",
            sha256="c" * 64,
            captured_at=now,
        )
        assert ev.id is not None
        assert ev.evidence_type == "snapshot"

        enrichment = service.record_enrichment(
            incident_id=incident.id,
            prompt_version="v2",
            status="completed",
            provider="gemini",
            model="gemini-1.5-pro",
            output={"summary": "Patient tripped over rug"},
            duration_ms=620,
            completed_at=now,
        )
        assert enrichment.id is not None
        assert enrichment.status == "completed"

        # Verify through incident retrieval
        loaded = service.get_incident(incident.id)
        assert len(loaded.evidence) == 1
        assert len(loaded.enrichments) == 1
        assert loaded.enrichments[0].model == "gemini-1.5-pro"

    def test_get_incident_not_found_raises(self, session_factory: sessionmaker[Session]) -> None:
        """Verify querying non-existent incident raises IncidentNotFoundError."""
        service = IncidentService(session_factory)
        with pytest.raises(IncidentNotFoundError):
            service.get_incident("non-existent-id")

    def test_list_incidents_via_service(self, session_factory: sessionmaker[Session]) -> None:
        """Verify list_incidents service query."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        for i in range(3):
            service.record_fall_incident(
                camera_id="cam-srv-list",
                track_id=f"trk-{i}",
                started_at=now,
                confirmed_at=now,
                fall_score=0.85,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )

        items, total = service.list_incidents(IncidentFilter(camera_id="cam-srv-list"))
        assert total == 3
        assert len(items) == 3

    def test_update_incident_lifecycle(self, session_factory: sessionmaker[Session]) -> None:
        """Verify updating lifecycle status through service."""
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        incident = service.record_fall_incident(
            camera_id="cam-lifecycle-srv",
            track_id="trk-40",
            started_at=now,
            confirmed_at=now,
            fall_score=0.92,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={},
        )

        updated = service.update_incident_lifecycle(
            incident_id=incident.id,
            detector_state="FALL_RECOVERED",
        )
        assert updated.detector_state == "FALL_RECOVERED"
        assert updated.fall_score == 0.92

    def test_transaction_rollback_on_failure(self) -> None:
        """Verify session rolls back cleanly if database operation fails."""
        mock_factory = MagicMock()
        mock_session = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_session
        mock_session.flush.side_effect = RuntimeError("Simulated DB flush crash")

        service = IncidentService(mock_factory)
        now = datetime.now(timezone.utc)

        with pytest.raises(RuntimeError, match="Simulated DB flush crash"):
            service.record_fall_incident(
                camera_id="cam-fail",
                track_id="trk-fail",
                started_at=now,
                confirmed_at=now,
                fall_score=0.9,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )

        # Assert rollback was executed
        mock_session.rollback.assert_called_once()
