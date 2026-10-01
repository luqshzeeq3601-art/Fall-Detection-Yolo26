"""Host telemetry collection for MQTT transport (P7-004).

Source-driven, stdlib-only collection (no psutil/torch dependency allowed):
  CPU count     — ``os.cpu_count()`` (guarded; ``None`` when unknown)
  Load average  — ``os.getloadavg()`` Unix-only (guarded; unitless 1m/5m/15m,
                  meaningful only beside ``cpu_count``)
  Memory        — Linux ``/proc/meminfo`` ``MemTotal``/``MemAvailable`` in kB,
                  converted to MB (guarded; ``None`` elsewhere)
  GPU/VRAM      — lazily-guarded ``torch.cuda`` import mirroring
                  ``api/routers/system.py`` (absent in CI → ``device="cpu"``,
                  VRAM ``None``)

Every reader NEVER raises: unavailable means ``None`` (unknown), never zero
and never a guess. ``camera_id`` is the topic attachment point supplied by
the caller (host stats are per-node; ``node`` carries the hostname or
``"unknown"``). Units: counts, load (unitless), MB, ISO-8601 UTC stamps.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from eldercare.mqtt.topics import SCHEMA_VERSION

HOST_SCHEMA_VERSION = SCHEMA_VERSION


@dataclass(frozen=True)
class HostTelemetry:
    """Point-in-time host telemetry; ``None`` means unknown."""

    node: str
    camera_id: str
    captured_at: str
    cpu_count: int | None = None
    load_avg_1m: float | None = None
    load_avg_5m: float | None = None
    load_avg_15m: float | None = None
    mem_total_mb: float | None = None
    mem_available_mb: float | None = None
    gpu_device: str | None = None
    gpu_name: str | None = None
    gpu_mem_allocated_mb: float | None = None
    gpu_mem_total_mb: float | None = None
    schema_version: str = HOST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe primitives; ``None``s preserved, never stringified."""
        return {
            "schema_version": self.schema_version,
            "node": self.node,
            "camera_id": self.camera_id,
            "captured_at": self.captured_at,
            "cpu_count": self.cpu_count,
            "load_avg_1m": self.load_avg_1m,
            "load_avg_5m": self.load_avg_5m,
            "load_avg_15m": self.load_avg_15m,
            "mem_total_mb": self.mem_total_mb,
            "mem_available_mb": self.mem_available_mb,
            "gpu_device": self.gpu_device,
            "gpu_name": self.gpu_name,
            "gpu_mem_allocated_mb": self.gpu_mem_allocated_mb,
            "gpu_mem_total_mb": self.gpu_mem_total_mb,
        }

    def to_json(self) -> str:
        """Serialize deterministically (sorted keys, no NaN)."""
        try:
            return json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"HostTelemetry is not JSON-serializable: {exc}") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_cpu_count() -> int | None:
    """Return logical CPU count, or ``None`` when undiscoverable."""
    try:
        count = os.cpu_count()
    except Exception:
        return None
    if not isinstance(count, int) or count < 1:
        return None
    return count


def read_loadavg() -> tuple[float | None, float | None, float | None]:
    """Return (1m, 5m, 15m) load averages, or ``None``s where unavailable."""
    getloadavg = getattr(os, "getloadavg", None)
    if getloadavg is None:
        return (None, None, None)
    try:
        one, five, fifteen = getloadavg()
    except Exception:
        return (None, None, None)
    values: list[float | None] = []
    for raw in (one, five, fifteen):
        if isinstance(raw, bool):
            values.append(None)
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            values.append(None)
            continue
        values.append(number if number >= 0 else None)
    one_v, five_v, fifteen_v = values
    return (one_v, five_v, fifteen_v)


def parse_meminfo(text: str) -> tuple[float | None, float | None]:
    """Parse Linux ``/proc/meminfo`` text into (total, available) MB."""
    total_kb: float | None = None
    available_kb: float | None = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3 or parts[2].lower() != "kb":
            continue
        try:
            value = float(parts[1])
        except ValueError:
            continue
        if parts[0].rstrip(":") == "MemTotal":
            total_kb = value
        elif parts[0].rstrip(":") == "MemAvailable":
            available_kb = value
    if total_kb is None or available_kb is None:
        return (None, None)
    return (total_kb / 1024.0, available_kb / 1024.0)


def read_meminfo_mb() -> tuple[float | None, float | None]:
    """Read host memory from ``/proc/meminfo``; ``(None, None)`` elsewhere."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return (None, None)
    return parse_meminfo(text)


def read_cuda() -> tuple[str | None, str | None, float | None, float | None]:
    """Return (device, name, allocated_MB, total_MB); CPU fallback on absence."""
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return ("cpu", None, None, None)
    try:
        if not torch.cuda.is_available():
            return ("cpu", None, None, None)
        name = str(torch.cuda.get_device_name(0))
        props = torch.cuda.get_device_properties(0)
        allocated = float(torch.cuda.memory_allocated(0)) / (1024 * 1024)
        total = float(props.total_memory) / (1024 * 1024)
    except Exception:
        return ("cpu", None, None, None)
    return ("cuda:0", name, allocated, total)


def collect_host_telemetry(
    camera_id: str,
    *,
    captured_at: str | None = None,
) -> HostTelemetry:
    """Collect host telemetry; every unavailable source stays ``None``."""
    if not isinstance(camera_id, str) or not camera_id:
        raise ValueError("camera_id must be a non-empty string")
    try:
        node = platform.node() or "unknown"
    except Exception:
        node = "unknown"
    load_1m, load_5m, load_15m = read_loadavg()
    mem_total, mem_available = read_meminfo_mb()
    gpu_device, gpu_name, gpu_allocated, gpu_total = read_cuda()
    return HostTelemetry(
        node=node,
        camera_id=camera_id,
        captured_at=captured_at or _utc_now_iso(),
        cpu_count=read_cpu_count(),
        load_avg_1m=load_1m,
        load_avg_5m=load_5m,
        load_avg_15m=load_15m,
        mem_total_mb=mem_total,
        mem_available_mb=mem_available,
        gpu_device=gpu_device,
        gpu_name=gpu_name,
        gpu_mem_allocated_mb=gpu_allocated,
        gpu_mem_total_mb=gpu_total,
    )


__all__ = [
    "HOST_SCHEMA_VERSION",
    "HostTelemetry",
    "collect_host_telemetry",
    "parse_meminfo",
    "read_cpu_count",
    "read_cuda",
    "read_loadavg",
    "read_meminfo_mb",
]
