"""Bridge from confirmed fall events to persisted incidents and async VLM enrichment.

Called from the synchronous detection loop when the temporal classifier confirms a
fall. It records the incident, stores keyframe evidence, and hands enrichment to the
AsyncEnrichmentService's event loop without waiting for it (ADR-003): the alert path
never blocks on, or is gated by, the VLM.
"""

from __future__ import annotations

import asyncio
import dataclasses
import numbers
from collections.abc import Sequence
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from eldercare.common.logger import get_logger
from eldercare.db.models import Incident
from eldercare.evidence.storage import EvidenceStorage
from eldercare.fall_engine.state_machine.states import FallEvent
from eldercare.incidents.service import IncidentService

if TYPE_CHECKING:
    from eldercare.agents.service import AsyncEnrichmentService

logger = get_logger("eldercare.incidents.bridge")


def _to_utc(timestamp: float) -> datetime:
    """Convert an epoch-seconds pipeline timestamp to an aware UTC datetime."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def _scalar_features(event: FallEvent) -> dict[str, Any]:
    """Flatten the event's top-level numeric features into a JSON-safe dict."""
    out: dict[str, Any] = {
        "confidence": float(event.confidence),
        "reason": event.reason,
    }
    feats = event.features
    if feats is not None and dataclasses.is_dataclass(feats):
        for f in dataclasses.fields(feats):
            value = getattr(feats, f.name)
            if isinstance(value, bool):
                out[f.name] = value
            elif isinstance(value, numbers.Real):
                out[f.name] = float(value)
    for key, value in event.metadata.items():
        out.setdefault(key, value)
    return out


def _encode_jpeg(frame: np.ndarray) -> bytes:
    """Validate a BGR frame (H, W, 3) uint8 and encode it as JPEG."""
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError(
            f"Keyframe must be a uint8 BGR array of shape (H, W, 3), "
            f"got shape={frame.shape} dtype={frame.dtype}"
        )
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("cv2.imencode failed to encode keyframe as JPEG")
    return buf.tobytes()


class FallIncidentBridge:
    """Persist confirmed fall events and schedule non-blocking VLM enrichment."""

    def __init__(
        self,
        incident_service: IncidentService,
        evidence_storage: EvidenceStorage,
        model_name: str,
        model_version: str,
        config_version: str,
        enrichment_service: AsyncEnrichmentService | None = None,
        enrichment_loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        if (enrichment_service is None) != (enrichment_loop is None):
            raise ValueError("enrichment_service and enrichment_loop must be given together")
        self._incidents = incident_service
        self._storage = evidence_storage
        self._model_name = model_name
        self._model_version = model_version
        self._config_version = config_version
        self._enrichment_service = enrichment_service
        self._enrichment_loop = enrichment_loop

    def handle_fall_event(
        self,
        event: FallEvent,
        keyframes: Sequence[np.ndarray] = (),
    ) -> Incident:
        """Record the incident, attach keyframes, and queue enrichment.

        Args:
            event: Confirmed fall event from the temporal classifier.
            keyframes: BGR frames stored as keyframe_00, keyframe_01, ... The
                orchestrator sends keyframe_00 to the VLM, so put the most informative
                frame (usually post-fall) first.

        Returns:
            The persisted Incident. Evidence or enrichment failures are logged and do
            not raise, so the alert is never lost because of them.
        """
        incident = self._incidents.record_fall_incident(
            camera_id=event.camera_id,
            track_id=str(event.track_id),
            started_at=_to_utc(event.candidate_timestamp),
            confirmed_at=_to_utc(event.confirmed_timestamp),
            fall_score=float(event.confidence),
            model_name=self._model_name,
            model_version=self._model_version,
            config_version=self._config_version,
            evidence_features=_scalar_features(event),
        )

        for idx, frame in enumerate(keyframes):
            try:
                rel_path, _, sha256 = self._storage.save_file(
                    f"{incident.camera_id}/{incident.id}/keyframe_{idx:02d}.jpg",
                    _encode_jpeg(frame),
                )
                self._incidents.attach_evidence(
                    incident_id=incident.id,
                    evidence_type="snapshot",
                    storage_path=rel_path,
                    mime_type="image/jpeg",
                    sha256=sha256,
                    captured_at=incident.confirmed_at,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to store keyframe evidence",
                    extra={"incident_id": incident.id, "index": idx, "error": str(exc)},
                )

        self._schedule_enrichment(incident)
        return incident

    def _schedule_enrichment(self, incident: Incident) -> None:
        """Submit the incident to the enrichment loop without waiting on the result."""
        if self._enrichment_service is None or self._enrichment_loop is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._enrichment_service.submit_incident(
                    incident_id=incident.id, camera_id=incident.camera_id
                ),
                self._enrichment_loop,
            )
        except RuntimeError as exc:  # loop closed
            logger.warning(
                "Enrichment loop unavailable; skipping enrichment",
                extra={"incident_id": incident.id, "error": str(exc)},
            )
            return

        incident_id = incident.id

        def _log_failure(fut: Future[Any]) -> None:
            if fut.cancelled():
                return
            exc = fut.exception()
            if exc is not None:
                logger.warning(
                    "Enrichment submission failed",
                    extra={"incident_id": incident_id, "error": str(exc)},
                )

        future.add_done_callback(_log_failure)
