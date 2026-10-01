"""Export human-reviewed incidents as a retraining manifest (active-learning loop).

Each record pairs the detector's decision with the caregiver's label, the VLM's
second opinion, and the keyframe evidence paths. Free-text review notes are left
out on purpose: they may contain personal details and are not training signal.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from eldercare.db.models import AgentEnrichment, Incident, IncidentReview

MANIFEST_SCHEMA_VERSION = "1.0.0"


def _iso_utc(ts: datetime) -> str:
    # SQLite returns naive datetimes; all stored timestamps are UTC.
    return (ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)).isoformat()


def _latest_review(incident: Incident) -> IncidentReview | None:
    if not incident.reviews:
        return None
    return max(incident.reviews, key=lambda r: (r.created_at, r.id))


def _latest_completed_enrichment(incident: Incident) -> AgentEnrichment | None:
    done = [e for e in incident.enrichments if e.status == "completed" and e.output]
    if not done:
        return None
    return max(done, key=lambda e: (e.completed_at or e.created_at, e.id))


def incident_to_record(incident: Incident) -> dict[str, Any] | None:
    """Build one manifest record, or None if the incident has no human review yet."""
    review = _latest_review(incident)
    if review is None:
        return None

    enrichment = _latest_completed_enrichment(incident)
    vlm: dict[str, Any] | None = None
    if enrichment is not None and enrichment.output is not None:
        vlm = {
            "fall_assessment": enrichment.output.get("fall_assessment"),
            "confidence_assessment": enrichment.output.get("confidence_assessment"),
            "provider": enrichment.provider,
            "model": enrichment.model,
            "prompt_version": enrichment.prompt_version,
        }

    vlm_verdict = vlm["fall_assessment"] if vlm else None
    vlm_agrees_with_human = (
        None
        if vlm_verdict not in ("fall", "no_fall") or review.label == "uncertain"
        else (vlm_verdict == "fall") == (review.label == "confirmed_fall")
    )

    keyframes = sorted(
        (
            {"path": ev.storage_path, "sha256": ev.sha256, "mime_type": ev.mime_type}
            for ev in incident.evidence
            if ev.evidence_type == "snapshot"
        ),
        key=lambda k: k["path"],
    )

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "incident_id": incident.id,
        "camera_id": incident.camera_id,
        "track_id": incident.track_id,
        "confirmed_at": _iso_utc(incident.confirmed_at),
        "detector": {
            "fall_score": incident.fall_score,
            "model_name": incident.model_name,
            "model_version": incident.model_version,
            "config_version": incident.config_version,
            "features": incident.evidence_features,
        },
        "human_label": review.label,
        # Every exported incident was raised by the detector, so a human "non_fall"
        # marks a detector false positive: the hard negatives retraining needs most.
        "detector_correct": (
            None if review.label == "uncertain" else review.label == "confirmed_fall"
        ),
        "reviewer": review.reviewer,
        "reviewed_at": _iso_utc(review.created_at),
        "vlm": vlm,
        "vlm_agrees_with_human": vlm_agrees_with_human,
        "keyframes": keyframes,
    }


def build_reviewed_dataset(
    session_factory: sessionmaker[Session],
    include_uncertain: bool = False,
) -> list[dict[str, Any]]:
    """Return manifest records for all reviewed incidents, oldest first."""
    with session_factory() as session:
        incidents = session.scalars(
            select(Incident)
            .options(
                selectinload(Incident.evidence),
                selectinload(Incident.reviews),
                selectinload(Incident.enrichments),
            )
            .order_by(Incident.confirmed_at, Incident.id)
        ).all()
        records = [incident_to_record(i) for i in incidents]

    return [
        r
        for r in records
        if r is not None and (include_uncertain or r["human_label"] != "uncertain")
    ]


def to_jsonl(records: Iterable[dict[str, Any]]) -> str:
    """Serialize records as JSON Lines."""
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)


def write_jsonl(records: list[dict[str, Any]], path: Path) -> int:
    """Write records to ``path`` as JSON Lines and return the number written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_jsonl(records), encoding="utf-8")
    return len(records)
