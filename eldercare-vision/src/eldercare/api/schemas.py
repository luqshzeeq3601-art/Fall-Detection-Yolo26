"""Pydantic schemas and error models for ElderCare Vision API (P5-004)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ==============================================================================
# Standard Error Envelope
# ==============================================================================


class ErrorDetail(BaseModel):
    """Detailed error object conforming to API_SPEC.md §7."""

    code: str = Field(..., description="Unique machine-readable error code")
    message: str = Field(..., description="Human-readable explanation of error")
    request_id: str | None = Field(
        default=None, description="Correlation UUID for tracing the request"
    )

    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """Unified error envelope across all API endpoints."""

    error: ErrorDetail

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# Health & Readiness Schemas
# ==============================================================================


class HealthResponse(BaseModel):
    """Liveness probe response model."""

    status: str = "ok"

    model_config = ConfigDict(extra="forbid")


class ReadyResponse(BaseModel):
    """Readiness probe response model detailing critical and optional dependencies."""

    status: str = "ready"
    database: str = "ready"
    vision_service: str = "ready"
    mqtt: str | None = None
    vlm: str | None = None

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# System Status Schemas
# ==============================================================================


class LatencySummary(BaseModel):
    """Latency metrics summary."""

    avg: float = Field(..., ge=0.0, description="Average inference latency in ms")
    p95: float = Field(..., ge=0.0, description="95th percentile inference latency in ms")

    model_config = ConfigDict(extra="forbid")


class GpuSummary(BaseModel):
    """GPU / Accelerator resource utilization."""

    device: str = Field(..., description="Compute device e.g. 'cuda:0' or 'cpu'")
    name: str = Field(..., description="Device name e.g. 'NVIDIA GeForce RTX 3070' or 'CPU'")
    memory_allocated_mb: float | None = Field(default=None, ge=0.0)
    memory_total_mb: float | None = Field(default=None, ge=0.0)

    model_config = ConfigDict(extra="forbid")


class SystemStatusResponse(BaseModel):
    """System runtime metadata and telemetry."""

    version: str = "1.0.0"
    model_name: str = "yolo26s-pose.pt"
    model_version: str = "1.0.0"
    config_version: str = "1.0.0"
    camera_count: int = Field(default=0, ge=0)
    vision_fps: float = Field(default=0.0, ge=0.0)
    inference_latency_ms: LatencySummary
    gpu_summary: GpuSummary
    integrations: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# Camera Schemas
# ==============================================================================


class CameraRead(BaseModel):
    """Public Camera model with guaranteed exclusion of sensitive RTSP credentials."""

    id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=255)
    status: str = Field(..., max_length=32)
    last_frame_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    reconnect_count: int = Field(default=0, ge=0)

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class CameraCreate(BaseModel):
    """Request payload for camera registration."""

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True
    status: str = "unknown"

    model_config = ConfigDict(extra="forbid")


class CameraUpdate(BaseModel):
    """Request payload for camera metadata updates."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    status: str | None = Field(default=None, min_length=1, max_length=32)

    model_config = ConfigDict(extra="forbid")
