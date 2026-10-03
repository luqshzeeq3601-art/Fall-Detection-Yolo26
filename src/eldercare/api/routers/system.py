"""System runtime telemetry and status router (P5-004)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eldercare.api.dependencies import get_db
from eldercare.api.schemas import (
    GpuSummary,
    LatencySummary,
    SystemStatusResponse,
)
from eldercare.db.models import Camera

router = APIRouter(tags=["System"])


def _get_hardware_summary() -> GpuSummary:
    """Detect available accelerator or fall back to CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            device_idx = 0
            device_name = torch.cuda.get_device_name(device_idx)
            props = torch.cuda.get_device_properties(device_idx)
            allocated = torch.cuda.memory_allocated(device_idx) / (1024 * 1024)
            total = props.total_memory / (1024 * 1024)
            return GpuSummary(
                device=f"cuda:{device_idx}",
                name=device_name,
                memory_allocated_mb=round(allocated, 2),
                memory_total_mb=round(total, 2),
            )
    except Exception:
        pass

    return GpuSummary(
        device="cpu",
        name="Host CPU",
        memory_allocated_mb=0.0,
        memory_total_mb=0.0,
    )


@router.get(
    "/system/status",
    response_model=SystemStatusResponse,
    summary="System Status & Telemetry",
    description="Retrieve system telemetry, versions, camera counts, and hardware summary.",
)
def get_system_status(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> SystemStatusResponse:
    """Return runtime metadata and measured stream telemetry (zeros when no stream runs)."""
    camera_count = db.scalar(select(func.count(Camera.id))) or 0
    gpu_info = _get_hardware_summary()
    manager = getattr(request.app.state, "live_manager", None)
    metrics = (
        manager.stream_metrics()
        if manager is not None
        else {"active_streams": 0, "fps": 0.0, "latency_avg_ms": 0.0, "latency_p95_ms": 0.0}
    )

    return SystemStatusResponse(
        version="1.0.0",
        model_name="yolo26s-pose.pt + v6_3_phase3b",
        model_version="6.3",
        config_version="frozen-v6.3",
        camera_count=camera_count,
        active_streams=metrics["active_streams"],
        vision_fps=metrics["fps"],
        inference_latency_ms=LatencySummary(
            avg=metrics["latency_avg_ms"], p95=metrics["latency_p95_ms"]
        ),
        gpu_summary=gpu_info,
        integrations={"mqtt": "disabled", "vlm": "disabled"},
    )
