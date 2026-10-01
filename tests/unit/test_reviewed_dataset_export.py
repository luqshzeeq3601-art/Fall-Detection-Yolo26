"""Tests for the reviewed-incident retraining manifest export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eldercare.db.base import Base
from eldercare.incidents.export import build_reviewed_dataset, to_jsonl, write_jsonl
from eldercare.incidents.service import IncidentService
from scripts.export_reviewed_dataset import main as export_main


def _incident(service: IncidentService, camera: str) -> str:
    now = datetime.now(timezone.utc)
    return service.record_fall_incident(
        camera_id=camera,
        track_id="1",
        started_at=now,
        confirmed_at=now,
        fall_score=0.9,
        model_name="v6_3_phase3b",
        model_version="6.3",
        config_version="test",
        evidence_features={"confidence": 0.9},
    ).id


@pytest.fixture
def db(tmp_path: Path) -> tuple[str, IncidentService, sessionmaker]:
    url = f"sqlite:///{(tmp_path / 'inc.db').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return url, IncidentService(factory), factory


def test_exports_only_reviewed_incidents_with_labels_and_vlm(db) -> None:
    _, service, factory = db
    real = _incident(service, "cam-a")
    false_alarm = _incident(service, "cam-b")
    _incident(service, "cam-c")  # never reviewed: not exported
    unsure = _incident(service, "cam-d")

    service.attach_evidence(
        incident_id=real,
        evidence_type="snapshot",
        storage_path="cam-a/x/keyframe_01.jpg",
        mime_type="image/jpeg",
        sha256="b" * 64,
        captured_at=datetime.now(timezone.utc),
    )
    service.attach_evidence(
        incident_id=real,
        evidence_type="snapshot",
        storage_path="cam-a/x/keyframe_00.jpg",
        mime_type="image/jpeg",
        sha256="a" * 64,
        captured_at=datetime.now(timezone.utc),
    )
    service.record_enrichment(
        incident_id=false_alarm,
        prompt_version="v1.1.0",
        status="completed",
        provider="ollama",
        model="local-vlm",
        output={"fall_assessment": "no_fall", "confidence_assessment": "high"},
    )
    service.submit_review(real, label="confirmed_fall", reviewer="nurse-1", notes="private")
    service.submit_review(false_alarm, label="non_fall")
    service.submit_review(unsure, label="uncertain")

    records = build_reviewed_dataset(factory)
    by_id = {r["incident_id"]: r for r in records}
    assert set(by_id) == {real, false_alarm}

    assert by_id[real]["human_label"] == "confirmed_fall"
    assert by_id[real]["detector_correct"] is True
    assert [k["path"] for k in by_id[real]["keyframes"]] == [
        "cam-a/x/keyframe_00.jpg",
        "cam-a/x/keyframe_01.jpg",
    ]
    assert by_id[real]["vlm"] is None
    assert "notes" not in by_id[real]  # free text is never exported

    fa = by_id[false_alarm]
    assert fa["detector_correct"] is False
    assert fa["vlm"]["fall_assessment"] == "no_fall"
    assert fa["vlm_agrees_with_human"] is True

    with_unsure = build_reviewed_dataset(factory, include_uncertain=True)
    assert {r["incident_id"] for r in with_unsure} == {real, false_alarm, unsure}
    unsure_rec = next(r for r in with_unsure if r["incident_id"] == unsure)
    assert unsure_rec["detector_correct"] is None


def test_latest_review_wins(db) -> None:
    _, service, factory = db
    inc = _incident(service, "cam-a")
    service.submit_review(inc, label="confirmed_fall")
    service.submit_review(inc, label="non_fall")
    (record,) = build_reviewed_dataset(factory)
    assert record["human_label"] == "non_fall"


def test_jsonl_roundtrip_and_cli(db, tmp_path: Path) -> None:
    url, service, factory = db
    inc = _incident(service, "cam-a")
    service.submit_review(inc, label="non_fall")

    text = to_jsonl(build_reviewed_dataset(factory))
    assert [json.loads(line)["incident_id"] for line in text.splitlines()] == [inc]

    out = tmp_path / "nested" / "out.jsonl"
    assert write_jsonl(build_reviewed_dataset(factory), out) == 1

    cli_out = tmp_path / "cli.jsonl"
    assert export_main(["--database-url", url, "--out", str(cli_out)]) == 0
    assert json.loads(cli_out.read_text(encoding="utf-8"))["human_label"] == "non_fall"
