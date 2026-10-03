"""FastAPI Application Factory with CORS, Request Tracking, and Error Model (P5-004)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from eldercare.api.dependencies import require_user
from eldercare.api.routers import (
    audit,
    cameras,
    health,
    incidents,
    live,
    system,
    websocket,
)
from eldercare.api.routers import auth as auth_router
from eldercare.api.routers import settings as settings_router
from eldercare.api.schemas import ErrorDetail, ErrorResponse
from eldercare.api.ws import ConnectionManager
from eldercare.db.session import create_db_engine, create_session_factory
from eldercare.evidence.storage import (
    ChecksumMismatchError,
    EvidenceFileNotFoundError,
    EvidenceStorage,
    PathTraversalError,
)
from eldercare.incidents.schemas import (
    CameraNotFoundError,
    EvidenceNotFoundError,
    IncidentNotFoundError,
    InvalidReviewLabelError,
)

if TYPE_CHECKING:
    from eldercare.agents.client import VLMProvider
    from eldercare.incidents.bridge import FallIncidentBridge
    from eldercare.mqtt.publisher import MqttPublisher

# Sentinel: build the VLM provider from VLM_* environment variables at startup.
_PROVIDER_FROM_ENV: object = object()

RETENTION_CHECK_SEC = 3600.0
ESCALATION_CHECK_SEC = 15.0
logger = logging.getLogger("eldercare.api.app")


def _runtime_lifespan(
    enrichment: Callable[[FastAPI], AbstractAsyncContextManager[None]],
    live_dirs: tuple[Path, Path | None] | None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Wrap the enrichment lifespan with the live video manager and retention purge."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with enrichment(app):
            app.state.main_loop = asyncio.get_running_loop()
            manager = None
            if live_dirs is not None:
                from eldercare.live.manager import LiveManager
                from eldercare.live.sources import SourceCatalog

                manager = LiveManager(
                    session_factory=app.state.session_factory,
                    catalog=SourceCatalog(upload_dir=live_dirs[0], sample_dir=live_dirs[1]),
                    connection_manager=app.state.connection_manager,
                    loop=app.state.main_loop,
                    bridge_factory=lambda: build_fall_incident_bridge(
                        app,
                        model_name="v6_3_phase3b",
                        model_version="6.3",
                        config_version="api-live",
                    ),
                )
            app.state.live_manager = manager
            retention = asyncio.create_task(_retention_loop(app)) if live_dirs else None
            escalation = asyncio.create_task(_escalation_loop(app))
            try:
                yield
            finally:
                escalation.cancel()
                if retention is not None:
                    retention.cancel()
                if manager is not None:
                    await asyncio.to_thread(manager.shutdown)
                app.state.live_manager = None

    return lifespan


async def _retention_loop(app: FastAPI) -> None:
    """Apply the workspace retention setting hourly."""
    from eldercare.api.workspace import load_workspace_settings
    from eldercare.incidents.retention import purge_expired_incidents

    while True:
        try:
            with app.state.session_factory() as session:
                days = load_workspace_settings(session).retention_days
            if days is not None:
                removed = await asyncio.to_thread(
                    purge_expired_incidents,
                    app.state.session_factory,
                    app.state.evidence_storage,
                    days,
                )
                if removed:
                    from eldercare.api.audit import record_audit

                    with app.state.session_factory() as session:
                        record_audit(
                            session,
                            "system",
                            "retention.purged",
                            detail={"incidents": removed, "older_than_days": days},
                        )
                        session.commit()
        except Exception:  # noqa: BLE001 - retry next cycle
            logger.exception("Retention purge failed")
        await asyncio.sleep(RETENTION_CHECK_SEC)


async def _escalation_loop(app: FastAPI) -> None:
    """Escalate confirmed falls nobody has responded to, using the workspace delay."""
    from eldercare.api.schemas import WebSocketEvent
    from eldercare.api.workspace import load_workspace_settings
    from eldercare.incidents.response import escalate_unanswered

    while True:
        await asyncio.sleep(ESCALATION_CHECK_SEC)
        try:
            with app.state.session_factory() as session:
                after = load_workspace_settings(session).escalate_after_sec
            if after is None:
                continue
            escalated = await asyncio.to_thread(
                escalate_unanswered, app.state.session_factory, after
            )
            for incident_id, camera_id in escalated:
                await app.state.connection_manager.broadcast(
                    WebSocketEvent(
                        event_type="incident.escalated",
                        camera_id=camera_id,
                        incident_id=incident_id,
                        payload={"after_sec": after},
                    )
                )
        except Exception:  # noqa: BLE001 - retry next cycle
            logger.exception("Escalation check failed")


def _enrichment_lifespan(
    vlm_provider: VLMProvider | None | object,
    mqtt_publisher: MqttPublisher | None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Lifespan that runs the async VLM enrichment workers alongside the API (ADR-003)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Imported lazily: eldercare.agents.orchestrator imports eldercare.api.
        from eldercare.agents.factory import build_vlm_provider_from_env
        from eldercare.agents.orchestrator import AgentEnrichmentOrchestrator
        from eldercare.agents.privacy import EvidencePrivacyBoundary
        from eldercare.agents.service import AsyncEnrichmentService
        from eldercare.incidents.service import IncidentService

        provider = (
            build_vlm_provider_from_env() if vlm_provider is _PROVIDER_FROM_ENV else vlm_provider
        )
        app.state.enrichment_service = None
        app.state.enrichment_loop = None
        if provider is None:
            yield
            return

        service = AsyncEnrichmentService()
        AgentEnrichmentOrchestrator(
            provider=provider,  # type: ignore[arg-type]
            service=service,
            incident_service=IncidentService(app.state.session_factory),
            privacy_boundary=EvidencePrivacyBoundary(
                evidence_root=app.state.evidence_storage.base_dir
            ),
            mqtt_publisher=mqtt_publisher,
            ws_manager=app.state.connection_manager,
        )
        await service.start()
        app.state.enrichment_service = service
        app.state.enrichment_loop = asyncio.get_running_loop()
        try:
            yield
        finally:
            await service.stop()
            app.state.enrichment_service = None
            app.state.enrichment_loop = None

    return lifespan


def build_fall_incident_bridge(
    app: FastAPI,
    model_name: str,
    model_version: str,
    config_version: str,
) -> FallIncidentBridge:
    """Create the bridge the detection loop calls on confirmed falls.

    Must be called after app startup so it picks up the running enrichment service.
    If enrichment is disabled, the bridge still records incidents and evidence.
    """
    from eldercare.incidents.bridge import FallIncidentBridge
    from eldercare.incidents.service import IncidentService

    return FallIncidentBridge(
        incident_service=IncidentService(app.state.session_factory),
        evidence_storage=app.state.evidence_storage,
        model_name=model_name,
        model_version=model_version,
        config_version=config_version,
        enrichment_service=getattr(app.state, "enrichment_service", None),
        enrichment_loop=getattr(app.state, "enrichment_loop", None),
    )


def _get_request_id(request: Request) -> str:
    """Extract or generate request correlation ID."""
    if hasattr(request.state, "request_id") and request.state.request_id:
        return str(request.state.request_id)
    return str(uuid.uuid4())


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    evidence_storage: EvidenceStorage | None = None,
    evidence_dir: Path | str = "evidence",
    connection_manager: ConnectionManager | None = None,
    cors_origins: list[str] | None = None,
    vlm_provider: VLMProvider | None | object = _PROVIDER_FROM_ENV,
    mqtt_publisher: MqttPublisher | None = None,
    require_auth: bool = False,
    upload_dir: Path | None = None,
    sample_dir: Path | None = None,
) -> FastAPI:
    """Create and configure the ElderCare Vision FastAPI application.

    VLM enrichment workers start with the app. By default the provider comes from
    ``VLM_PROVIDER`` (default ``none``, i.e. disabled); pass ``vlm_provider`` to
    override, or ``None`` to disable explicitly.

    ``require_auth`` gates every data route behind an operator session cookie.
    Passing ``upload_dir`` enables live video (webcam and file streams) at startup.
    """
    app = FastAPI(
        title="ElderCare Vision API",
        version="1.0.0",
        description="Real-time Fall Detection and Incident Persistence API for ElderCare Vision.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_runtime_lifespan(
            _enrichment_lifespan(vlm_provider, mqtt_publisher),
            None if upload_dir is None else (upload_dir, sample_dir),
        ),
    )

    # Initialize state dependencies
    app.state.require_auth = require_auth
    app.state.live_manager = None
    if session_factory is None:
        engine = create_db_engine()
        session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory

    if evidence_storage is None:
        evidence_storage = EvidenceStorage(base_dir=evidence_dir)
    app.state.evidence_storage = evidence_storage

    if connection_manager is None:
        connection_manager = ConnectionManager()
    app.state.connection_manager = connection_manager

    # 1. CORS Middleware
    origins = cors_origins or ["http://127.0.0.1:5173", "http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Request ID & Security Headers Middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # 3. Standardized Error Handlers conforming to API_SPEC.md §7
    @app.exception_handler(CameraNotFoundError)
    async def camera_not_found_handler(request: Request, exc: CameraNotFoundError) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="CAMERA_NOT_FOUND",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(IncidentNotFoundError)
    async def incident_not_found_handler(
        request: Request, exc: IncidentNotFoundError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INCIDENT_NOT_FOUND",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(EvidenceNotFoundError)
    async def evidence_not_found_handler(
        request: Request, exc: EvidenceNotFoundError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="EVIDENCE_NOT_FOUND",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(EvidenceFileNotFoundError)
    async def evidence_file_not_found_handler(
        request: Request, exc: EvidenceFileNotFoundError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="EVIDENCE_FILE_NOT_FOUND",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(PathTraversalError)
    async def path_traversal_handler(request: Request, exc: PathTraversalError) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="PATH_TRAVERSAL_FORBIDDEN",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(ChecksumMismatchError)
    async def checksum_mismatch_handler(
        request: Request, exc: ChecksumMismatchError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="CHECKSUM_MISMATCH",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(InvalidReviewLabelError)
    async def invalid_review_label_handler(
        request: Request, exc: InvalidReviewLabelError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INVALID_REVIEW_LABEL",
                    message=str(exc),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        req_id = _get_request_id(request)
        # Format human-friendly validation message without leaking internals
        errors = exc.errors()
        msg = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in errors
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message=f"Request validation failed: {msg}",
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=f"HTTP_{exc.status_code}",
                    message=str(exc.detail),
                    request_id=req_id,
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = _get_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_SERVER_ERROR",
                    message="An internal server error occurred.",
                    request_id=req_id,
                )
            ).model_dump(),
        )

    # 4. Mount Routers at root and /api/v1
    protected = [Depends(require_user)]
    for prefix in ("", "/api/v1"):
        app.include_router(health.router, prefix=prefix)
        app.include_router(auth_router.router, prefix=prefix)
        app.include_router(system.router, prefix=prefix, dependencies=protected)
        app.include_router(cameras.router, prefix=prefix, dependencies=protected)
        app.include_router(incidents.router, prefix=prefix, dependencies=protected)
        app.include_router(live.router, prefix=prefix, dependencies=protected)
        app.include_router(settings_router.router, prefix=prefix, dependencies=protected)
        app.include_router(audit.router, prefix=prefix, dependencies=protected)
        app.include_router(websocket.router, prefix=prefix)

    return app
