"""Unit tests for IncidentRepository (P5-002)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eldercare.db.base import Base
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import (
    AgentEnrichmentCreate,
    CameraNotFoundError,
    IncidentCreate,
    IncidentEvidenceCreate,
    IncidentFilter,
    IncidentNotFoundError,
)


@pytest.fixture
def db_session() -> Session:
    """Create an isolated SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


class TestIncidentRepository:
    """Test suite verifying data access, queries, filters, and relations."""

    def test_camera_auto_provisioning_and_lookup(self, db_session: Session) -> None:
        """Verify get_or_create_camera provisions new camera or returns existing."""
        repo = IncidentRepository(db_session)
        cam = repo.get_or_create_camera("cam-101", name="Hallway North")
        assert cam.id == "cam-101"
        assert cam.name == "Hallway North"

        cam2 = repo.get_or_create_camera("cam-101", name="Ignored Name")
        assert cam2.id == "cam-101"
        assert cam2.name == "Hallway North"

    def test_create_incident_requires_camera(self, db_session: Session) -> None:
        """Verify create_incident raises CameraNotFoundError if camera is missing."""
        repo = IncidentRepository(db_session)
        now = datetime.now(timezone.utc)
        payload = IncidentCreate(
            camera_id="cam-missing",
            track_id="trk-1",
            started_at=now,
            confirmed_at=now,
            fall_score=0.95,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"angle": 30.0},
        )
        with pytest.raises(CameraNotFoundError):
            repo.create_incident(payload)

    def test_create_and_get_incident_with_relations(self, db_session: Session) -> None:
        """Verify creating an incident, attaching evidence/reviews, and eager retrieval."""
        repo = IncidentRepository(db_session)
        repo.get_or_create_camera("cam-102")

        now = datetime.now(timezone.utc)
        incident_id = str(uuid.uuid4())
        payload = IncidentCreate(
            id=incident_id,
            camera_id="cam-102",
            track_id="trk-2",
            started_at=now,
            confirmed_at=now,
            fall_score=0.87,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"velocity": 0.62},
        )
        incident = repo.create_incident(payload)
        assert incident.id == incident_id

        # Attach evidence
        ev_payload = IncidentEvidenceCreate(
            evidence_type="snapshot",
            storage_path="/data/evidence/test.jpg",
            mime_type="image/jpeg",
            sha256="a" * 64,
            captured_at=now,
        )
        repo.add_evidence(incident_id, ev_payload)

        # Attach review
        repo.add_review(
            incident_id=incident_id,
            label="confirmed_fall",
            notes="Real fall verified",
            reviewer="operator_1",
        )

        # Attach enrichment
        enr_payload = AgentEnrichmentCreate(
            prompt_version="v1",
            status="completed",
            provider="gemini",
            model="gemini-1.5-flash",
            output={"assessment": "Fall confirmed"},
        )
        repo.add_enrichment(incident_id, enr_payload)

        db_session.commit()

        # Query incident with eager relations
        loaded = repo.get_incident_by_id(incident_id, load_relations=True)
        assert loaded is not None
        assert loaded.id == incident_id
        assert len(loaded.evidence) == 1
        assert len(loaded.reviews) == 1
        assert len(loaded.enrichments) == 1
        assert loaded.reviews[0].label == "confirmed_fall"
        assert loaded.evidence[0].sha256 == "a" * 64

    def test_list_incidents_filtering_and_pagination(self, db_session: Session) -> None:
        """Verify filtering by camera_id, status, dates, review_label, and pagination."""
        repo = IncidentRepository(db_session)
        repo.get_or_create_camera("cam-A")
        repo.get_or_create_camera("cam-B")

        base_time = datetime(2026, 9, 23, 10, 0, 0, tzinfo=timezone.utc)

        # Create 5 incidents
        for i in range(5):
            inc_id = f"inc-00{i}"
            cam_id = "cam-A" if i < 3 else "cam-B"
            conf_time = base_time + timedelta(minutes=i * 10)
            status = "FALL_CONFIRMED" if i % 2 == 0 else "FALL_RECOVERED"

            repo.create_incident(
                IncidentCreate(
                    id=inc_id,
                    camera_id=cam_id,
                    track_id=f"trk-{i}",
                    started_at=conf_time - timedelta(seconds=2),
                    confirmed_at=conf_time,
                    detector_state=status,
                    fall_score=0.8 + (i * 0.03),
                    model_name="yolo26s-pose.pt",
                    model_version="1.0.0",
                    config_version="1.0.0",
                    evidence_features={},
                )
            )

            # Add reviews to some
            if i in (0, 1):
                repo.add_review(inc_id, label="confirmed_fall", reviewer="nurse_1")
            if i == 1:
                # Add second review to test deduplication
                repo.add_review(inc_id, label="confirmed_fall", reviewer="supervisor_1")
            elif i == 2:
                repo.add_review(inc_id, label="non_fall", reviewer="nurse_2")

        db_session.commit()

        # 1. Test Camera filter
        results, total = repo.list_incidents(IncidentFilter(camera_id="cam-A"))
        assert total == 3
        assert len(results) == 3
        assert all(r.camera_id == "cam-A" for r in results)

        # 2. Test Status filter
        results, total = repo.list_incidents(IncidentFilter(status="FALL_RECOVERED"))
        assert total == 2
        assert len(results) == 2

        # 3. Test Date range filter
        results, total = repo.list_incidents(
            IncidentFilter(
                from_time=base_time + timedelta(minutes=15),
                to_time=base_time + timedelta(minutes=35),
            )
        )
        assert total == 2  # inc-002 (20m), inc-003 (30m)

        # 4. Test Review Label filter (with deduplication check for inc-001)
        results, total = repo.list_incidents(IncidentFilter(review_label="confirmed_fall"))
        assert total == 2  # inc-000, inc-001
        assert len(results) == 2
        assert {r.id for r in results} == {"inc-000", "inc-001"}

        # 5. Test Pagination
        results_page1, total = repo.list_incidents(IncidentFilter(limit=2, offset=0))
        assert total == 5
        assert len(results_page1) == 2

        results_page2, total = repo.list_incidents(IncidentFilter(limit=2, offset=2))
        assert total == 5
        assert len(results_page2) == 2
        assert results_page1[0].id != results_page2[0].id

    def test_update_incident_state_and_not_found(self, db_session: Session) -> None:
        """Verify updating mutable lifecycle fields and error on missing incident."""
        repo = IncidentRepository(db_session)
        repo.get_or_create_camera("cam-103")

        now = datetime.now(timezone.utc)
        repo.create_incident(
            IncidentCreate(
                id="inc-lifecycle",
                camera_id="cam-103",
                track_id="trk-3",
                started_at=now,
                confirmed_at=now,
                fall_score=0.91,
                model_name="yolo26s-pose.pt",
                model_version="1.0.0",
                config_version="1.0.0",
                evidence_features={},
            )
        )
        db_session.commit()

        ended_time = now + timedelta(seconds=15)
        updated = repo.update_incident_state(
            "inc-lifecycle", ended_at=ended_time, detector_state="FALL_RECOVERED"
        )
        assert updated.ended_at == ended_time
        assert updated.detector_state == "FALL_RECOVERED"
        # Verify detector core fields unchanged
        assert updated.fall_score == 0.91
        assert updated.model_name == "yolo26s-pose.pt"

        with pytest.raises(IncidentNotFoundError):
            repo.update_incident_state("inc-does-not-exist", detector_state="UNKNOWN")

    def test_evidence_and_review_not_found_handling(self, db_session: Session) -> None:
        """Verify adding evidence or reviews to missing incident raises IncidentNotFoundError."""
        repo = IncidentRepository(db_session)
        now = datetime.now(timezone.utc)

        with pytest.raises(IncidentNotFoundError):
            repo.add_evidence(
                "missing-inc",
                IncidentEvidenceCreate(
                    evidence_type="snapshot",
                    storage_path="/data/foo.jpg",
                    mime_type="image/jpeg",
                    sha256="b" * 64,
                    captured_at=now,
                ),
            )

        with pytest.raises(IncidentNotFoundError):
            repo.add_review("missing-inc", label="confirmed_fall")
