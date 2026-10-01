"""Integration test connecting EvidenceStorage to IncidentService persistence (P5-003)."""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eldercare.db.base import Base
from eldercare.evidence.storage import EvidenceStorage, get_mime_type
from eldercare.incidents.service import IncidentService


class TestEvidencePersistenceIntegration:
    """Integration test suite combining media storage and incident database persistence."""

    def test_save_evidence_and_persist_incident_record(self, tmp_path: Path) -> None:
        """Verify saving media to disk, calculating SHA-256, persisting to database,

        and loading/verifying content.
        """
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)

        storage = EvidenceStorage(base_dir=tmp_path / "app_evidence")
        service = IncidentService(session_factory)
        now = datetime.now(timezone.utc)

        # 1. Create Incident in DB
        incident = service.record_fall_incident(
            camera_id="cam-evidence-int",
            track_id="trk-ev-1",
            started_at=now,
            confirmed_at=now,
            fall_score=0.97,
            model_name="yolo26s-pose.pt",
            model_version="1.0.0",
            config_version="1.0.0",
            evidence_features={"angle": 15.0},
        )

        # 2. Write Snapshot Evidence to Storage
        raw_image_data = b"\xff\xd8\xff\xe0" + (b"\x12" * 500)
        rel_path, _, sha256_digest = storage.save_file(
            relative_path=f"cam-evidence-int/{incident.id}/fall_snapshot.jpg",
            content=raw_image_data,
        )

        # 3. Attach Evidence to Incident in DB
        ev_record = service.attach_evidence(
            incident_id=incident.id,
            evidence_type="snapshot",
            storage_path=rel_path,
            mime_type=get_mime_type(rel_path),
            sha256=sha256_digest,
            captured_at=now,
        )

        assert ev_record.storage_path == rel_path
        assert ev_record.sha256 == sha256_digest
        assert ev_record.mime_type == "image/jpeg"

        # 4. Read back and verify from disk using DB metadata
        fetched_incident = service.get_incident(incident.id)
        assert len(fetched_incident.evidence) == 1
        db_ev = fetched_incident.evidence[0]

        # Verify disk integrity with DB hash
        assert storage.verify_file_integrity(db_ev.storage_path, db_ev.sha256) is True
        loaded_bytes = storage.read_file(db_ev.storage_path, verify_sha256=db_ev.sha256)
        assert loaded_bytes == raw_image_data

        Base.metadata.drop_all(engine)
