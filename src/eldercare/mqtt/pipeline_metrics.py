"""Pipeline telemetry snapshots for MQTT transport (P7-003).

A snapshot is a TYPED PAYLOAD, not an event-envelope event: EVENT_SCHEMA.md
§2 enumerates discrete event types and none covers periodic telemetry, so
snapshots ride the ``health`` topic as versioned data (``schema_version``)
rather than polluting the event vocabulary or consumer event logs.

Ownership rule: this module MEASURES NOTHING. Every field is assembled from
caller-supplied typed sources — P1-006 ``CaptureSnapshot`` and P2-005
``PoseTiming`` — preserving their ``None``-means-unknown semantics exactly.
``None`` is unknown, never zero; no rate/latency is ever fabricated.

Units (explicit):
  fps                         — frames per second (``capture_fps``)
  ms                          — milliseconds (``inference_*_ms``)
  counts                      — monotonic totals (queue/reconnect fields)
  state                       — lowercase health string (``health_state``)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from eldercare.mqtt.topics import SCHEMA_VERSION, build_topic

SNAPSHOT_SCHEMA_VERSION = SCHEMA_VERSION


@dataclass(frozen=True)
class PipelineMetrics:
    """Point-in-time pipeline telemetry; ``None`` means unknown."""

    camera_id: str
    captured_at: str
    capture_fps: float | None = None
    inference_predict_ms: float | None = None
    inference_adapt_ms: float | None = None
    inference_total_ms: float | None = None
    queue_submitted: int | None = None
    queue_dropped: int | None = None
    queue_depth: int | None = None
    reconnect_attempts: int | None = None
    reconnect_failures: int | None = None
    health_state: str | None = None
    schema_version: str = SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe primitives; ``None``s preserved, never stringified."""
        return {
            "schema_version": self.schema_version,
            "camera_id": self.camera_id,
            "captured_at": self.captured_at,
            "capture_fps": self.capture_fps,
            "inference_predict_ms": self.inference_predict_ms,
            "inference_adapt_ms": self.inference_adapt_ms,
            "inference_total_ms": self.inference_total_ms,
            "queue_submitted": self.queue_submitted,
            "queue_dropped": self.queue_dropped,
            "queue_depth": self.queue_depth,
            "reconnect_attempts": self.reconnect_attempts,
            "reconnect_failures": self.reconnect_failures,
            "health_state": self.health_state,
        }

    def to_json(self) -> str:
        """Serialize deterministically (sorted keys, no NaN)."""
        try:
            return json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"PipelineMetrics is not JSON-serializable: {exc}") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collect_pipeline_metrics(
    camera_id: str,
    *,
    capture: Any | None = None,
    timing: Any | None = None,
    captured_at: str | None = None,
) -> PipelineMetrics:
    """Assemble a snapshot from existing typed sources (duck-typed).

    ``capture`` is a P1-006 ``CaptureSnapshot`` (or compatible object);
    ``timing`` is a P2-005 ``PoseTiming`` (or compatible object). Either may
    be ``None`` (source unavailable → fields stay unknown). Never raises on
    missing attributes: unknown stays ``None``.
    """
    if not isinstance(camera_id, str) or not camera_id:
        raise ValueError("camera_id must be a non-empty string")
    inferred: dict[str, Any] = {
        "predict_ms": None,
        "adapt_ms": None,
        "total_ms": None,
    }
    if timing is not None:
        try:
            raw = timing.to_dict()
        except AttributeError:
            raw = {}
        if isinstance(raw, dict):
            for key in ("predict_ms", "adapt_ms", "total_ms"):
                value = raw.get(key)
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    inferred[key] = float(value)

    def _field(name: str) -> Any | None:
        return getattr(capture, name, None) if capture is not None else None

    return PipelineMetrics(
        camera_id=camera_id,
        captured_at=captured_at or _utc_now_iso(),
        capture_fps=_field("capture_fps"),
        inference_predict_ms=inferred["predict_ms"],
        inference_adapt_ms=inferred["adapt_ms"],
        inference_total_ms=inferred["total_ms"],
        queue_submitted=_field("queue_submitted"),
        queue_dropped=_field("queue_dropped"),
        queue_depth=_field("queue_depth"),
        reconnect_attempts=_field("reconnect_attempts"),
        reconnect_failures=_field("reconnect_failures"),
        health_state=_field("health_state"),
    )


def snapshot_topic(site_id: str, camera_id: str) -> str:
    """Return the health topic carrying pipeline snapshots."""
    return build_topic(site_id, camera_id, "health")


# Re-exported for a stable import surface; field kept for linters.
__all__ = [
    "PipelineMetrics",
    "SNAPSHOT_SCHEMA_VERSION",
    "collect_pipeline_metrics",
    "snapshot_topic",
]
