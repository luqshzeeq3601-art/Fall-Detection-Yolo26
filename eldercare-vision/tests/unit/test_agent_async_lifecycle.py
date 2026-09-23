"""Unit tests for asynchronous Agent/VLM enrichment lifecycle and worker (P10-001)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from eldercare.agents.service import AsyncEnrichmentService
from eldercare.agents.state import EnrichmentJob, EnrichmentStatus


class TestEnrichmentJobState:
    """Test state machine transitions of EnrichmentJob."""

    def test_job_initialization_defaults(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        assert job.incident_id == "inc-001"
        assert job.camera_id == "cam-01"
        assert job.status == EnrichmentStatus.PENDING
        assert job.started_at is None
        assert job.completed_at is None
        assert job.output is None
        assert job.duration_ms is None

    def test_mark_in_progress(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        job.mark_in_progress()
        assert job.status == EnrichmentStatus.IN_PROGRESS
        assert job.started_at is not None

        # Cannot transition to in_progress twice
        with pytest.raises(ValueError, match="Cannot transition to in_progress"):
            job.mark_in_progress()

    def test_mark_completed(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        job.mark_in_progress()
        job.mark_completed(output={"summary": "Person fallen on floor"}, duration_ms=120)
        assert job.status == EnrichmentStatus.COMPLETED
        assert job.completed_at is not None
        assert job.output == {"summary": "Person fallen on floor"}
        assert job.duration_ms == 120

    def test_mark_failed(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        job.mark_in_progress()
        job.mark_failed(error_code="PROVIDER_ERROR", error_message="API connection refused")
        assert job.status == EnrichmentStatus.FAILED
        assert job.error_code == "PROVIDER_ERROR"
        assert job.error_message == "API connection refused"
        assert job.completed_at is not None

    def test_mark_timed_out(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        job.mark_in_progress()
        job.mark_timed_out("Request took > 10s")
        assert job.status == EnrichmentStatus.TIMED_OUT
        assert job.error_code == "TIMEOUT"
        assert job.error_message == "Request took > 10s"

    def test_mark_skipped(self) -> None:
        job = EnrichmentJob(incident_id="inc-001", camera_id="cam-01")
        job.mark_skipped("LOW_CONFIDENCE")
        assert job.status == EnrichmentStatus.SKIPPED
        assert job.error_code == "LOW_CONFIDENCE"
        assert job.duration_ms == 0


class TestAsyncEnrichmentService:
    """Test async worker queue, non-blocking submission, concurrency, and failure isolation."""

    @pytest.mark.asyncio
    async def test_non_blocking_submission_and_execution(self) -> None:
        processed_jobs: list[str] = []

        async def mock_processor(job: EnrichmentJob) -> dict[str, Any]:
            await asyncio.sleep(0.01)
            processed_jobs.append(job.incident_id)
            return {"posture": "prone", "incident_id": job.incident_id}

        service = AsyncEnrichmentService(processor=mock_processor, max_queue_size=10)
        await service.start(num_workers=1)

        job = await service.submit_incident(incident_id="inc-100", camera_id="cam-01")
        assert job is not None
        assert job.status in (EnrichmentStatus.PENDING, EnrichmentStatus.IN_PROGRESS)

        # Wait briefly for worker to complete
        for _ in range(50):
            if job.status == EnrichmentStatus.COMPLETED:
                break
            await asyncio.sleep(0.01)

        assert job.status == EnrichmentStatus.COMPLETED
        assert job.output == {"posture": "prone", "incident_id": "inc-100"}
        assert "inc-100" in processed_jobs

        await service.stop()

    @pytest.mark.asyncio
    async def test_idempotent_duplicate_submission(self) -> None:
        gate = asyncio.Event()

        async def slow_processor(job: EnrichmentJob) -> dict[str, Any]:
            await gate.wait()
            return {"status": "ok"}

        service = AsyncEnrichmentService(processor=slow_processor, max_queue_size=10)
        await service.start(num_workers=1)

        # First submission
        job1 = await service.submit_incident(incident_id="inc-200", camera_id="cam-01")
        assert job1 is not None

        # Duplicate submission while first is still pending/in-progress
        job2 = await service.submit_incident(incident_id="inc-200", camera_id="cam-01")
        assert job2 is not None
        assert job1.job_id == job2.job_id  # Same job returned (deduplicated)

        gate.set()
        await asyncio.sleep(0.05)
        await service.stop()

    @pytest.mark.asyncio
    async def test_concurrency_limiting(self) -> None:
        active_concurrent = 0
        max_seen_concurrent = 0

        async def concurrent_processor(job: EnrichmentJob) -> dict[str, Any]:
            nonlocal active_concurrent, max_seen_concurrent
            active_concurrent += 1
            max_seen_concurrent = max(max_seen_concurrent, active_concurrent)
            await asyncio.sleep(0.02)
            active_concurrent -= 1
            return {"id": job.incident_id}

        service = AsyncEnrichmentService(
            processor=concurrent_processor,
            max_concurrency=2,
            max_queue_size=20,
        )
        await service.start(num_workers=4)

        for i in range(6):
            await service.submit_incident(incident_id=f"inc-c-{i}", camera_id="cam-01")

        await asyncio.sleep(0.15)
        assert max_seen_concurrent <= 2  # Respects max_concurrency semaphore
        await service.stop()

    @pytest.mark.asyncio
    async def test_failure_isolation_processor_exception(self) -> None:
        async def failing_processor(job: EnrichmentJob) -> dict[str, Any]:
            raise RuntimeError("Upstream VLM network error")

        service = AsyncEnrichmentService(processor=failing_processor)
        await service.start(num_workers=1)

        job = await service.submit_incident(incident_id="inc-fail-1", camera_id="cam-01")
        assert job is not None

        for _ in range(50):
            if job.status == EnrichmentStatus.FAILED:
                break
            await asyncio.sleep(0.01)

        assert job.status == EnrichmentStatus.FAILED
        assert job.error_code == "PROCESSOR_ERROR"
        assert "Upstream VLM network error" in (job.error_message or "")

        # Service is still running and can process next job
        assert service.is_running
        await service.stop()

    @pytest.mark.asyncio
    async def test_queue_full_drop_behavior(self) -> None:
        block_event = asyncio.Event()

        async def blocked_processor(job: EnrichmentJob) -> dict[str, Any]:
            await block_event.wait()
            return {}

        # Queue capacity = 1
        service = AsyncEnrichmentService(processor=blocked_processor, max_queue_size=1)
        await service.start(num_workers=1)

        j1 = await service.submit_incident(incident_id="inc-q1", camera_id="cam-01")
        # Yield to allow worker to dequeue j1 and enter blocked_processor
        await asyncio.sleep(0.01)

        j2 = await service.submit_incident(incident_id="inc-q2", camera_id="cam-01")
        # j1 is running in worker, j2 occupies the 1 queue slot. Next submission should drop safely.
        j3 = await service.submit_incident(incident_id="inc-q3", camera_id="cam-01")

        assert j1 is not None
        assert j2 is not None
        assert j3 is None  # Dropped without crashing

        block_event.set()
        await asyncio.sleep(0.05)
        await service.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self) -> None:
        service = AsyncEnrichmentService()
        await service.start(num_workers=2)
        assert service.is_running
        await service.stop()
        assert not service.is_running
