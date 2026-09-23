"""Versioned MQTT event envelope for ElderCare Vision (P7-002).

Common envelope (EVENT_SCHEMA.md §1)::

    event_id, event_type, schema_version, occurred_at, source,
    camera_id, incident_id, payload

Serialization is deterministic: ``json.dumps`` with sorted keys, compact
separators, and ``allow_nan=False`` (NaN/Infinity are rejected, never
silently emitted). Parsing tolerates unknown additive fields (EVENT_SCHEMA
§5: consumers ignore them) but rejects missing/invalid core fields.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from eldercare.mqtt.topics import SCHEMA_VERSION


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class MqttEvent:
    """Immutable versioned event for MQTT transport."""

    event_id: str
    event_type: str
    schema_version: str
    occurred_at: str
    source: str
    camera_id: str | None
    incident_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        source: str = "vision-service",
        camera_id: str | None = None,
        incident_id: str | None = None,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
    ) -> MqttEvent:
        """Create an event with generated id/timestamp unless supplied."""
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")
        if not source or not isinstance(source, str):
            raise ValueError("source must be a non-empty string")
        stamp = occurred_at or _utc_now_iso()
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"occurred_at must be ISO-8601, got {stamp!r}") from exc
        if parsed.tzinfo is None:
            raise ValueError("occurred_at must carry timezone information")
        return cls(
            event_id=event_id or str(uuid.uuid4()),
            event_type=event_type,
            schema_version=SCHEMA_VERSION,
            occurred_at=stamp,
            source=source,
            camera_id=camera_id,
            incident_id=incident_id,
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the envelope as plain JSON-safe data."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at,
            "source": self.source,
            "camera_id": self.camera_id,
            "incident_id": self.incident_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        """Serialize deterministically (sorted keys, no NaN)."""
        try:
            return json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MqttEvent payload is not JSON-serializable: {exc}") from exc

    @classmethod
    def from_json(cls, raw: str | bytes) -> MqttEvent:
        """Parse an envelope, ignoring unknown additive fields."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Malformed event JSON: {exc}") from exc
        except RecursionError as exc:
            raise ValueError("Event JSON exceeds supported nesting depth") from exc
        if not isinstance(data, dict):
            raise ValueError("Event JSON must be an object")
        for key in ("event_id", "event_type", "schema_version", "occurred_at", "source"):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f"Event field {key!r} must be a non-empty string")
        try:
            stamp = datetime.fromisoformat(str(data["occurred_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Event field 'occurred_at' must be ISO-8601") from exc
        if stamp.tzinfo is None:
            raise ValueError("Event field 'occurred_at' must carry timezone information")
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("Event field 'payload' must be an object")
        for key in ("camera_id", "incident_id"):
            value = data.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Event field {key!r} must be a string or null")
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            schema_version=data["schema_version"],
            occurred_at=data["occurred_at"],
            source=data["source"],
            camera_id=data.get("camera_id"),
            incident_id=data.get("incident_id"),
            payload=payload,
        )
