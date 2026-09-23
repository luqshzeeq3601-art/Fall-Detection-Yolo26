"""Unit tests for SQLAlchemy persistence models (P5-001)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from eldercare.db.base import Base
from eldercare.db.models import (
    AgentEnrichment,
    Camera,
    Incident,
    IncidentEvidence,
    IncidentReview,
)


@pytest.fixture
def db_session() -> Session:
    """Create an isolated in-memory SQLite database session for model testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


class TestDatabaseModels:
    """Test suite verifying ORM models, relationships, and constraints."""

    def test_camera_crud_and_defaults(self, db_session: Session) -> None:
        """Verify Camera creation, default values, and repr."""
        camera = Camera(
            id="cam-test-01",
            name="Living Room Camera",
        )
        db_session.add(camera)
        db_session.commit()

        queried = db_session.scalar(select(Camera).where(Camera.id == "cam-test-01"))
        assert queried is not None
        assert queried.name == "Living Room Camera"
        assert queried.enabled is True
        assert queried.status == "unknown"
        assert queried.reconnect_count == 0
        assert queried.created_at is not None
        assert queried.updated_at is not None
        assert "cam-test-01" in repr(queried)

    def test_incident_and_cascade_relationships(self, db_session: Session) -> None:
        """Verify Incident creation and cascade deletion of evidence, reviews, and enrichments."""
        camera = Camera(id="cam-01", name="Hallway Camera", status="online")
        db_session.add(camera)
        db_session.commit()

        now = datetime.now(timezone.utc)
        incident_id = str(uuid.uuid4())
        incident = Incident(
            id=incident_id,
            camera_id="cam-01",
            track_id="1",
            started_at=now,
            confirmed_at=now,
            detector_state="FALL_CONFIRMED",
            fall_score=0.92,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"descent_velocity": 0.85, "torso_angle": 15.0},
        )
        db_session.add(incident)
        db_session.commit()

        # Add evidence
        evidence = IncidentEvidence(
            incident_id=incident_id,
            evidence_type="snapshot",
            storage_path="/data/evidence/snap1.jpg",
            mime_type="image/jpeg",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            captured_at=now,
        )
        # Add review
        review = IncidentReview(
            incident_id=incident_id,
            label="confirmed_fall",
            notes="Real fall scenario",
            reviewer="nurse_01",
        )
        # Add enrichment
        enrichment = AgentEnrichment(
            incident_id=incident_id,
            status="completed",
            provider="gemini",
            model="gemini-1.5-flash",
            prompt_version="v1",
            output={"narrative": "Person fell forward"},
            duration_ms=450,
            completed_at=now,
        )
        db_session.add_all([evidence, review, enrichment])
        db_session.commit()

        # Query and verify associations
        saved_incident = db_session.scalar(select(Incident).where(Incident.id == incident_id))
        assert saved_incident is not None
        assert len(saved_incident.evidence) == 1
        assert len(saved_incident.reviews) == 1
        assert len(saved_incident.enrichments) == 1
        assert saved_incident.evidence[0].evidence_type == "snapshot"
        assert saved_incident.reviews[0].label == "confirmed_fall"
        assert saved_incident.enrichments[0].output == {"narrative": "Person fell forward"}
        assert "Incident" in repr(saved_incident)

        # Delete incident and assert cascade
        db_session.delete(saved_incident)
        db_session.commit()

        assert db_session.scalar(select(Incident).where(Incident.id == incident_id)) is None
        assert (
            db_session.scalar(
                select(IncidentEvidence).where(IncidentEvidence.incident_id == incident_id)
            )
            is None
        )
        assert (
            db_session.scalar(
                select(IncidentReview).where(IncidentReview.incident_id == incident_id)
            )
            is None
        )
        assert (
            db_session.scalar(
                select(AgentEnrichment).where(AgentEnrichment.incident_id == incident_id)
            )
            is None
        )

    def test_append_only_review_ledger(self, db_session: Session) -> None:
        """Verify multiple reviews can be attached to one incident without overwriting."""
        camera = Camera(id="cam-02", name="Bedroom Camera")
        now = datetime.now(timezone.utc)
        incident = Incident(
            id="inc-review-test",
            camera_id="cam-02",
            track_id="2",
            started_at=now,
            confirmed_at=now,
            detector_state="FALL_CONFIRMED",
            fall_score=0.88,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"aspect_ratio": 0.6},
        )
        db_session.add_all([camera, incident])
        db_session.commit()

        review1 = IncidentReview(
            incident_id="inc-review-test",
            label="uncertain",
            notes="First assessment",
            reviewer="operator_a",
        )
        review2 = IncidentReview(
            incident_id="inc-review-test",
            label="confirmed_fall",
            notes="Second assessment after video review",
            reviewer="supervisor_b",
        )
        db_session.add_all([review1, review2])
        db_session.commit()

        reviews = list(
            db_session.scalars(
                select(IncidentReview)
                .where(IncidentReview.incident_id == "inc-review-test")
                .order_by(IncidentReview.created_at)
            )
        )
        assert len(reviews) == 2
        assert reviews[0].label == "uncertain"
        assert reviews[1].label == "confirmed_fall"
