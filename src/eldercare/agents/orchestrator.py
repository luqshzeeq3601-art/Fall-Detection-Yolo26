"""Agent/VLM enrichment orchestrator for service, DB, MQTT, and WebSockets (P10-005)."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eldercare.agents.client import (
    ProviderClientError,
    ProviderTimeoutError,
    VLMProvider,
)
from eldercare.agents.privacy import (
    EvidencePrivacyBoundary,
    PrivacyBoundaryError,
)
from eldercare.agents.prompts import DEFAULT_PROMPT_VERSION, build_enrichment_prompt
from eldercare.agents.schemas import parse_and_validate_enrichment_output
from eldercare.agents.service import AsyncEnrichmentService
from eldercare.agents.state import EnrichmentJob
from eldercare.api.schemas import WebSocketEvent
from eldercare.api.ws import ConnectionManager
from eldercare.common.logger import get_logger
from eldercare.common.redaction import sanitize_exception_message
from eldercare.incidents.service import IncidentService
from eldercare.mqtt.publisher import MqttPublisher

logger = get_logger("eldercare.agents.orchestrator")


class AgentEnrichmentOrchestrator:
    """Orchestrates end-to-end asynchronous Agent/VLM enrichment pipelines.

    Coordinates:
    - Privacy boundary sanitation (evidence validation and secret stripping).
    - Versioned prompt assembly.
    - VLM provider execution with retry and timeout policies.
    - Strict Pydantic output schema validation.
    - Isolated persistence to the database (`agent_enrichments` table).
    - Asynchronous event broadcast over MQTT and WebSockets.
    """

    def __init__(
        self,
        provider: VLMProvider,
        service: AsyncEnrichmentService | None = None,
        incident_service: IncidentService | None = None,
        privacy_boundary: EvidencePrivacyBoundary | None = None,
        evidence_root: str | Path | None = None,
        mqtt_publisher: MqttPublisher | None = None,
        ws_manager: ConnectionManager | None = None,
        prompt_version: str = DEFAULT_PROMPT_VERSION,
    ) -> None:
        self.provider = provider
        self.incident_service = incident_service

        if privacy_boundary is not None:
            self.privacy_boundary = privacy_boundary
        else:
            root = evidence_root or os.getenv("EVIDENCE_STORAGE_PATH", "/tmp/evidence")
            self.privacy_boundary = EvidencePrivacyBoundary(evidence_root=root)

        self.mqtt_publisher = mqtt_publisher
        self.ws_manager = ws_manager
        self.prompt_version = prompt_version

        # Wire processor into the async service
        self.service = service or AsyncEnrichmentService(processor=self.process_job)
        self.service.processor = self.process_job

    async def process_job(self, job: EnrichmentJob) -> dict[str, Any] | None:
        """Execute enrichment processing for a single queued job.

        Returns:
            Validated enrichment output dictionary.

        Raises:
            Exception on unrecoverable worker failure.
        """
        start_mono = time.monotonic()
        sanitized_context: dict[str, Any] = {
            "incident_id": job.incident_id,
            "camera_id": job.camera_id,
        }

        # Step 1: Query incident metadata for context if incident_service is available
        media_path: str | None = None
        if self.incident_service is not None:
            try:
                incident = self.incident_service.get_incident(job.incident_id, load_relations=True)
                sanitized_context["fall_score"] = float(incident.fall_score)
                sanitized_context["timestamp"] = incident.confirmed_at.isoformat()
                # Deterministic choice: relation order is by random UUID, so sort by path
                # (the bridge names snapshots keyframe_00, keyframe_01, ...).
                evidence = sorted(getattr(incident, "evidence", []), key=lambda e: e.storage_path)
                for ev in evidence:
                    if ev.evidence_type == "snapshot" and ev.storage_path:
                        try:
                            valid_path = self.privacy_boundary.validate_and_resolve_media_path(
                                ev.storage_path
                            )
                            media_path = str(valid_path)
                            break
                        except PrivacyBoundaryError as pe:
                            logger.warning(
                                "Snapshot rejected by privacy boundary",
                                extra={"incident_id": job.incident_id, "error": str(pe)},
                            )
            except Exception as exc:
                logger.warning(
                    "Failed to load incident for enrichment context",
                    extra={"incident_id": job.incident_id, "error": str(exc)},
                )

        # Step 2: Assemble versioned prompt
        prompt = build_enrichment_prompt(
            context=sanitized_context,
            prompt_version=self.prompt_version,
        )

        # Step 3: Call VLM provider with error handling and DB persistence
        try:
            raw_response = await self.provider.generate_enrichment(
                prompt=prompt,
                media_path=media_path,
                context=sanitized_context,
            )

            # Step 4: Strict schema validation
            validated_output = parse_and_validate_enrichment_output(raw_response)
            output_dict = validated_output.model_dump(mode="json")

            duration_ms = max(0, int((time.monotonic() - start_mono) * 1000.0))
            completed_at = datetime.now(timezone.utc)

            # Step 5: Persist successful enrichment in database
            if self.incident_service is not None:
                try:
                    self.incident_service.record_enrichment(
                        incident_id=job.incident_id,
                        prompt_version=self.prompt_version,
                        status="completed",
                        provider=self.provider.provider_name,
                        model=self.provider.model_name,
                        output=output_dict,
                        duration_ms=duration_ms,
                        completed_at=completed_at,
                    )
                except Exception as db_exc:
                    logger.error(
                        "Failed to persist completed enrichment in database",
                        extra={"incident_id": job.incident_id, "error": str(db_exc)},
                    )

            # Step 6: Broadcast events via MQTT & WebSockets
            await self._broadcast_events(
                event_type="agent.enrichment.completed",
                incident_id=job.incident_id,
                camera_id=job.camera_id,
                payload=output_dict,
            )

            return output_dict

        except (ProviderTimeoutError, TimeoutError) as timeout_exc:
            duration_ms = max(0, int((time.monotonic() - start_mono) * 1000.0))
            err_msg = sanitize_exception_message(str(timeout_exc))
            self._record_failure(
                job=job,
                status="timed_out",
                error_code="TIMEOUT",
                error_message=err_msg,
                duration_ms=duration_ms,
            )
            await self._broadcast_events(
                event_type="agent.enrichment.failed",
                incident_id=job.incident_id,
                camera_id=job.camera_id,
                payload={"error_code": "TIMEOUT", "error_message": err_msg},
            )
            raise

        except ProviderClientError as provider_exc:
            duration_ms = max(0, int((time.monotonic() - start_mono) * 1000.0))
            err_code = provider_exc.__class__.__name__.upper()
            err_msg = sanitize_exception_message(str(provider_exc))
            self._record_failure(
                job=job,
                status="failed",
                error_code=err_code,
                error_message=err_msg,
                duration_ms=duration_ms,
            )
            await self._broadcast_events(
                event_type="agent.enrichment.failed",
                incident_id=job.incident_id,
                camera_id=job.camera_id,
                payload={"error_code": err_code, "error_message": err_msg},
            )
            raise

        except Exception as exc:
            duration_ms = max(0, int((time.monotonic() - start_mono) * 1000.0))
            err_msg = sanitize_exception_message(str(exc))
            self._record_failure(
                job=job,
                status="failed",
                error_code="UNEXPECTED_ERROR",
                error_message=err_msg,
                duration_ms=duration_ms,
            )
            await self._broadcast_events(
                event_type="agent.enrichment.failed",
                incident_id=job.incident_id,
                camera_id=job.camera_id,
                payload={"error_code": "UNEXPECTED_ERROR", "error_message": err_msg},
            )
            raise

    def _record_failure(
        self,
        job: EnrichmentJob,
        status: str,
        error_code: str,
        error_message: str,
        duration_ms: int,
    ) -> None:
        """Persist failed enrichment status to database if incident service is configured."""
        if self.incident_service is not None:
            try:
                self.incident_service.record_enrichment(
                    incident_id=job.incident_id,
                    prompt_version=self.prompt_version,
                    status=status,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    error_code=error_code,
                    duration_ms=duration_ms,
                    completed_at=datetime.now(timezone.utc),
                )
            except Exception as db_exc:
                logger.error(
                    "Failed to persist failed enrichment status to database",
                    extra={"incident_id": job.incident_id, "error": str(db_exc)},
                )

    async def _broadcast_events(
        self,
        event_type: str,
        incident_id: str,
        camera_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Broadcast events over MQTT and WebSockets in a non-blocking, isolated manner."""
        # MQTT Broadcast
        if self.mqtt_publisher is not None:
            try:
                self.mqtt_publisher.publish_agent(
                    event_type=event_type,
                    camera_id=camera_id,
                    incident_id=incident_id,
                    payload=payload,
                )
            except Exception as mqtt_exc:
                logger.warning(
                    "MQTT agent event publish failed",
                    extra={"incident_id": incident_id, "error": str(mqtt_exc)},
                )

        # WebSocket Broadcast
        if self.ws_manager is not None:
            try:
                ws_event = WebSocketEvent(
                    event_type=event_type,
                    camera_id=camera_id,
                    incident_id=incident_id,
                    payload=payload,
                )
                await self.ws_manager.broadcast(ws_event)
            except Exception as ws_exc:
                logger.warning(
                    "WebSocket agent event broadcast failed",
                    extra={"incident_id": incident_id, "error": str(ws_exc)},
                )
