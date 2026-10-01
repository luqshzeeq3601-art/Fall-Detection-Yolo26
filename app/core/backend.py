"""Local incident backend for the Streamlit demo.

Wires the same production pieces the API uses: SQLite incident store, sandboxed
evidence storage, FallIncidentBridge, and the async VLM enrichment workers (on a
background event loop, so Streamlit's script thread never waits on the VLM).
The VLM is chosen by ``VLM_PROVIDER`` (default ``none``: second opinion off).
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

from eldercare.agents.client import VLMProvider
from eldercare.agents.factory import build_vlm_provider_from_env
from eldercare.agents.orchestrator import AgentEnrichmentOrchestrator
from eldercare.agents.privacy import EvidencePrivacyBoundary
from eldercare.agents.schemas import enrichment_needs_review
from eldercare.agents.service import AsyncEnrichmentService
from eldercare.db.base import Base
from eldercare.db.models import Incident
from eldercare.db.session import create_db_engine, create_session_factory
from eldercare.evidence.storage import EvidenceStorage
from eldercare.fall_engine.state_machine.states import FallEvent
from eldercare.incidents.bridge import FallIncidentBridge
from eldercare.incidents.export import build_reviewed_dataset, to_jsonl
from eldercare.incidents.repository import IncidentRepository
from eldercare.incidents.schemas import IncidentFilter
from eldercare.incidents.service import IncidentService

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "demo_data"

# Keyframe i was captured KEYFRAME_OFFSETS_SEC[i] seconds before the alert.
# keyframe_00 (the moment of the alert) is the one sent to the VLM.
KEYFRAME_OFFSETS_SEC: tuple[float, ...] = (0.0, 1.5, 3.0)

REVIEW_LABELS: dict[str, str] = {
    "confirmed_fall": "Real fall",
    "non_fall": "Not a fall",
    "uncertain": "Can't tell",
}


@dataclass(frozen=True)
class EnrichmentView:
    status: str
    output: dict[str, Any] | None
    provider: str | None
    model: str | None
    prompt_version: str
    error_code: str | None
    duration_ms: int | None


@dataclass(frozen=True)
class ReviewView:
    label: str
    reviewer: str | None
    notes: str | None
    created_at: datetime


@dataclass(frozen=True)
class IncidentView:
    id: str
    camera_id: str
    confirmed_at: datetime
    fall_score: float
    keyframes: tuple[Path, ...]  # absolute paths, keyframe_00 first
    enrichment: EnrichmentView | None
    reviews: tuple[ReviewView, ...]  # oldest first

    @property
    def latest_review(self) -> ReviewView | None:
        return self.reviews[-1] if self.reviews else None

    @property
    def flagged_by_ai(self) -> bool:
        e = self.enrichment
        return e is not None and e.status == "completed" and enrichment_needs_review(e.output)

    @property
    def needs_review(self) -> bool:
        return self.latest_review is None


def _utc(ts: datetime) -> datetime:
    """SQLite drops tzinfo; stored values are UTC."""
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _to_view(incident: Incident, evidence_root: Path) -> IncidentView:
    snapshots = sorted(
        (ev for ev in incident.evidence if ev.evidence_type == "snapshot"),
        key=lambda ev: ev.storage_path,
    )
    enrichments = sorted(incident.enrichments, key=lambda e: (e.created_at, e.id))
    latest = enrichments[-1] if enrichments else None
    return IncidentView(
        id=incident.id,
        camera_id=incident.camera_id,
        confirmed_at=_utc(incident.confirmed_at),
        fall_score=incident.fall_score,
        keyframes=tuple(evidence_root / ev.storage_path for ev in snapshots),
        enrichment=(
            None
            if latest is None
            else EnrichmentView(
                status=latest.status,
                output=latest.output,
                provider=latest.provider,
                model=latest.model,
                prompt_version=latest.prompt_version,
                error_code=latest.error_code,
                duration_ms=latest.duration_ms,
            )
        ),
        reviews=tuple(
            ReviewView(
                label=r.label, reviewer=r.reviewer, notes=r.notes, created_at=_utc(r.created_at)
            )
            for r in sorted(incident.reviews, key=lambda r: (r.created_at, r.id))
        ),
    )


class DemoBackend:
    """Owns the demo's incident store, evidence files and VLM enrichment workers."""

    def __init__(self, data_dir: Path, provider: VLMProvider | None) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self._engine = create_db_engine(f"sqlite:///{(data_dir / 'eldercare_demo.db').as_posix()}")
        Base.metadata.create_all(self._engine)
        self.session_factory = create_session_factory(self._engine)
        self.storage = EvidenceStorage(base_dir=data_dir / "evidence")
        self.incidents = IncidentService(self.session_factory)
        self.provider = provider

        service: AsyncEnrichmentService | None = None
        loop: asyncio.AbstractEventLoop | None = None
        if provider is not None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name="vlm-enrichment", daemon=True).start()
            service = AsyncEnrichmentService(max_queue_size=50, max_concurrency=1)
            AgentEnrichmentOrchestrator(
                provider=provider,
                service=service,
                incident_service=self.incidents,
                privacy_boundary=EvidencePrivacyBoundary(evidence_root=self.storage.base_dir),
            )
            asyncio.run_coroutine_threadsafe(service.start(num_workers=1), loop).result(timeout=5)

        self.bridge = FallIncidentBridge(
            incident_service=self.incidents,
            evidence_storage=self.storage,
            model_name="v6_3_phase3b",
            model_version="6.3",
            config_version="streamlit-demo",
            enrichment_service=service,
            enrichment_loop=loop,
        )

    @property
    def vlm_enabled(self) -> bool:
        return self.provider is not None

    @property
    def vlm_label(self) -> str:
        if self.provider is None:
            return "Off"
        return f"{self.provider.model_name} ({self.provider.provider_name})"

    def record_fall(
        self,
        event: FallEvent,
        camera_id: str,
        keyframes: Sequence[np.ndarray],
    ) -> str:
        """Persist a fall confirmed by the demo and queue the VLM second opinion.

        Demo clips carry video-relative timestamps, so the event is re-stamped to
        wall-clock time, keeping the gap between onset and confirmation.
        """
        now = time.time()
        stamped = replace(
            event,
            camera_id=camera_id,
            confirmed_timestamp=now,
            candidate_timestamp=now - (event.confirmed_timestamp - event.candidate_timestamp),
            down_start_timestamp=now - (event.confirmed_timestamp - event.down_start_timestamp),
        )
        return self.bridge.handle_fall_event(stamped, keyframes).id

    def list_incidents(self) -> list[IncidentView]:
        """All incidents, newest first."""
        with self.session_factory() as session:
            items, _ = IncidentRepository(session).list_incidents(
                IncidentFilter(limit=500), load_relations=True
            )
            return [_to_view(i, self.storage.base_dir) for i in items]

    def submit_review(
        self, incident_id: str, label: str, reviewer: str | None, notes: str | None
    ) -> None:
        self.incidents.submit_review(
            incident_id, label=label, reviewer=reviewer or None, notes=notes or None
        )

    def export_reviewed_jsonl(self) -> tuple[str, int]:
        """Retraining manifest of reviewed incidents (JSONL text, record count)."""
        records = build_reviewed_dataset(self.session_factory)
        return to_jsonl(records), len(records)


@st.cache_resource(show_spinner=False)
def get_backend() -> DemoBackend:
    """Process-wide backend; ``DEMO_DATA_DIR`` overrides where data is kept."""
    data_dir = Path(os.getenv("DEMO_DATA_DIR", str(DEFAULT_DATA_DIR)))
    return DemoBackend(data_dir=data_dir, provider=build_vlm_provider_from_env())
