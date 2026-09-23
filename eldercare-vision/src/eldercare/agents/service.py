"""Asynchronous, non-blocking job runner for Agent/VLM enrichment (P10-001).

Guarantees full decoupling from the real-time deterministic fall detection
pipeline. Core vision processing never blocks on or awaits enrichment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from eldercare.agents.state import EnrichmentJob, EnrichmentStatus
from eldercare.common.logger import get_logger

logger = get_logger("eldercare.agents.service")

# Type alias for the pluggable job processor callable:
# async def processor(job: EnrichmentJob) -> dict[str, Any]
JobProcessor = Callable[[EnrichmentJob], Awaitable[dict[str, Any] | None]]


class AsyncEnrichmentService:
    """Asynchronous worker service managing incident enrichment job lifecycles.

    Features:
    - Bounded in-memory FIFO queue to prevent unbounded memory growth.
    - Configurable concurrency limit via semaphore.
    - Idempotent submission: deduplicates in-flight incident enrichments.
    - Total failure isolation: worker exceptions never escape or impact callers.
    - Clean graceful shutdown handling.
    """

    def __init__(
        self,
        processor: JobProcessor | None = None,
        max_queue_size: int = 500,
        max_concurrency: int = 4,
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError(f"max_queue_size must be positive, got {max_queue_size}")
        if max_concurrency <= 0:
            raise ValueError(f"max_concurrency must be positive, got {max_concurrency}")

        self._processor = processor
        self._max_queue_size = max_queue_size
        self._max_concurrency = max_concurrency

        self._queue: asyncio.Queue[EnrichmentJob] = asyncio.Queue(maxsize=max_queue_size)
        self._active_jobs: dict[str, EnrichmentJob] = {}
        self._completed_jobs: dict[str, EnrichmentJob] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency)

        self._worker_tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Return True if background worker tasks are active."""
        return self._running

    @property
    def processor(self) -> JobProcessor | None:
        """Return the configured job processor."""
        return self._processor

    @processor.setter
    def processor(self, proc: JobProcessor | None) -> None:
        """Set or update the job processor callable."""
        self._processor = proc

    @property
    def queue_size(self) -> int:
        """Current number of queued jobs waiting for execution."""
        return self._queue.qsize()

    @property
    def active_job_count(self) -> int:
        """Number of jobs currently pending or in-progress."""
        return len(self._active_jobs)

    async def start(self, num_workers: int = 2) -> None:
        """Start background worker tasks."""
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._shutdown_event.clear()
            self._worker_tasks = [
                asyncio.create_task(self._worker_loop(worker_idx=i), name=f"enrichment-worker-{i}")
                for i in range(num_workers)
            ]
            logger.info(
                "AsyncEnrichmentService started",
                extra={"workers": num_workers, "max_concurrency": self._max_concurrency},
            )

    async def stop(self, timeout_seconds: float = 5.0) -> None:
        """Gracefully stop background worker tasks and wait for in-flight jobs."""
        async with self._lock:
            if not self._running:
                return
            self._running = False
            self._shutdown_event.set()

        # Cancel idle workers waiting on empty queue
        for task in self._worker_tasks:
            task.cancel()

        # Await worker termination
        if self._worker_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._worker_tasks, return_exceptions=True),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning("AsyncEnrichmentService shutdown timed out; forced stop")
            self._worker_tasks.clear()

        logger.info("AsyncEnrichmentService stopped")

    async def submit_incident(
        self,
        incident_id: str,
        camera_id: str,
    ) -> EnrichmentJob | None:
        """Submit an incident for asynchronous enrichment.

        Non-blocking: Returns immediately without awaiting VLM execution.
        Idempotent: If the incident is already pending or in progress, returns
        the existing job to avoid duplicate inference.

        Returns:
            EnrichmentJob instance, or None if the queue is full.
        """
        if not incident_id or not camera_id:
            raise ValueError("incident_id and camera_id must be non-empty strings")

        async with self._lock:
            # Idempotency check: return existing in-flight job if already present
            if incident_id in self._active_jobs:
                logger.debug(
                    "Enrichment job already in flight; deduplicating",
                    extra={"incident_id": incident_id},
                )
                return self._active_jobs[incident_id]

            job = EnrichmentJob(incident_id=incident_id, camera_id=camera_id)

            try:
                self._queue.put_nowait(job)
                self._active_jobs[incident_id] = job
                logger.info(
                    "Enrichment job queued",
                    extra={
                        "job_id": job.job_id,
                        "incident_id": incident_id,
                        "camera_id": camera_id,
                    },
                )
                return job
            except asyncio.QueueFull:
                logger.warning(
                    "Enrichment queue is full; dropping job",
                    extra={"incident_id": incident_id, "queue_size": self._queue.qsize()},
                )
                job.mark_failed(
                    error_code="QUEUE_FULL",
                    error_message=f"Enrichment queue capacity ({self._max_queue_size}) exceeded",
                )
                return None

    def get_job_by_incident_id(self, incident_id: str) -> EnrichmentJob | None:
        """Lookup an active or completed job by incident identifier."""
        return self._active_jobs.get(incident_id) or self._completed_jobs.get(incident_id)

    async def _worker_loop(self, worker_idx: int) -> None:
        """Internal worker task loop reading and executing queued jobs."""
        while self._running and not self._shutdown_event.is_set():
            try:
                # Wait for next available job
                job = await self._queue.get()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "Unexpected error reading from enrichment queue",
                    extra={"worker": worker_idx, "error": str(exc)},
                )
                continue

            try:
                await self._process_single_job(job)
            except Exception as exc:
                # Top-level failure barrier: worker MUST NOT crash
                logger.error(
                    "Uncaught exception during job processing",
                    extra={
                        "job_id": job.job_id,
                        "incident_id": job.incident_id,
                        "error": str(exc),
                    },
                )
                if (
                    job.status == EnrichmentStatus.IN_PROGRESS
                    or job.status == EnrichmentStatus.PENDING
                ):
                    job.mark_failed(error_code="UNCAUGHT_WORKER_ERROR", error_message=str(exc))
            finally:
                self._queue.task_done()
                async with self._lock:
                    self._active_jobs.pop(job.incident_id, None)
                    # Keep bounded completed job cache (last 1000 items)
                    self._completed_jobs[job.incident_id] = job
                    if len(self._completed_jobs) > 1000:
                        oldest_key = next(iter(self._completed_jobs))
                        self._completed_jobs.pop(oldest_key, None)

    async def _process_single_job(self, job: EnrichmentJob) -> None:
        """Execute a single job with concurrency limiting and status transitions."""
        async with self._semaphore:
            job.mark_in_progress()

            if self._processor is None:
                # Default no-op processor for testing / baseline
                job.mark_completed(output={"message": "No-op enrichment complete"})
                return

            try:
                output = await self._processor(job)
                if output is not None:
                    job.mark_completed(output=output)
                else:
                    job.mark_skipped(reason="PROCESSOR_RETURNED_NONE")
            except asyncio.TimeoutError:
                job.mark_timed_out("Enrichment processor timed out")
            except Exception as exc:
                job.mark_failed(error_code="PROCESSOR_ERROR", error_message=str(exc))
