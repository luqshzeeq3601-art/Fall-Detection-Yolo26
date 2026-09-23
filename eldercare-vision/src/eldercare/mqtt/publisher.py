"""Versioned MQTT publisher for ElderCare Vision (P7-002).

Topic → event-type mapping (EVENT_SCHEMA.md §§2/4):

===================  ============================  ==================
Category (topic)     Event types                   Default QoS
===================  ============================  ==================
``events/fall``      ``fall.*``                     1 (spec-mandated)
``health``           ``camera.*``, ``incident.*``,  1 (inside the
                     ``service.*``                   spec 0-or-1 allowance)
``agent``            ``agent.*``                     1 (unspecified → at-least-once)
===================  ============================  ==================

``retained`` defaults to ``False`` everywhere (the spec is silent; delivery
semantics stay explicit per call). The publisher keeps bounded counters only
and holds NO queues: publishing while disconnected fails fast with
:exc:`TransportError` so callers (P7-005) decide retry/drop policy and the
core detector never blocks on the broker.

Production transport note: any object implementing :class:`MqttTransport`
works. The production adapter (paho-mqtt ``Client``: ``connect(host, port,
keepalive)`` / ``publish(topic, payload, qos, retain)`` with rc check /
``disconnect()``) is intentionally NOT vendored — paho-mqtt is absent from
the locked environment and unit CI must not need a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.topics import TopicCategory, build_topic

DEFAULT_QOS: dict[str, int] = {
    "events/fall": 1,
    "health": 1,
    "agent": 1,
}

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "rtsp_url",
        "rtsp",
        "password",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "authorization",
        "stack_trace",
        "traceback",
    }
)


class TransportError(Exception):
    """Raised when the MQTT transport cannot connect or publish."""


class MqttTransport(Protocol):
    """Minimal broker-transport surface the publisher needs."""

    def connect(self) -> None: ...
    def publish(self, topic: str, payload: str, qos: int = 0, retained: bool = False) -> None: ...
    def disconnect(self) -> None: ...


@dataclass(frozen=True)
class PublishReceipt:
    """Proof of a handed-off publish (broker ack semantics stay with QoS)."""

    topic: str
    qos: int
    retained: bool
    event_id: str


class TelemetrySnapshot(Protocol):
    """Structural surface for versioned telemetry snapshots (P7-003/P7-004)."""

    camera_id: str
    captured_at: str
    schema_version: str

    def to_dict(self) -> dict[str, Any]: ...
    def to_json(self) -> str: ...


def _assert_safe_payload(payload: dict[str, Any], *, _path: str = "$") -> None:
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError(f"Payload keys must be strings at {_path}")
        if key.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"Payload must not carry sensitive field {key!r} at {_path}")
        if isinstance(value, dict):
            _assert_safe_payload(value, _path=f"{_path}.{key}")


class MqttPublisher:
    """Versioned event publisher over an injectable transport."""

    def __init__(
        self,
        site_id: str,
        transport: MqttTransport,
        source: str = "vision-service",
    ) -> None:
        if not isinstance(site_id, str) or not site_id:
            raise ValueError("site_id must be a non-empty string")
        if not isinstance(source, str) or not source:
            raise ValueError("source must be a non-empty string")
        self._site_id = site_id
        self._source = source
        self._transport = transport
        self._connected = False
        self.published_count = 0
        self.failed_count = 0

    @property
    def site_id(self) -> str:
        """Return the configured site identifier."""
        return self._site_id

    @property
    def source(self) -> str:
        """Return the configured event source name."""
        return self._source

    @property
    def connected(self) -> bool:
        """Return whether this publisher holds an open transport."""
        return self._connected

    def connect(self) -> None:
        """Open the underlying transport (raises TransportError on failure)."""
        try:
            self._transport.connect()
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"MQTT connect failed: {exc}") from exc
        self._connected = True

    def disconnect(self) -> None:
        """Close the underlying transport; never raises."""
        try:
            self._transport.disconnect()
        except Exception:
            pass
        self._connected = False

    def publish_event(
        self,
        event: MqttEvent,
        category: TopicCategory,
        qos: int | None = None,
        retained: bool = False,
    ) -> PublishReceipt:
        """Serialize and hand one versioned event to the transport."""
        if not self._connected:
            raise TransportError("Publisher is not connected")
        if qos is None:
            qos = DEFAULT_QOS[category]
        if qos not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {qos!r}")
        _assert_safe_payload(event.payload)
        topic = build_topic(self._site_id, event.camera_id or "system", category)
        payload = event.to_json()
        try:
            self._transport.publish(topic, payload, qos=qos, retained=retained)
        except TransportError:
            self.failed_count += 1
            raise
        except Exception as exc:
            self.failed_count += 1
            raise TransportError(f"MQTT publish failed: {exc}") from exc
        self.published_count += 1
        return PublishReceipt(topic=topic, qos=qos, retained=retained, event_id=event.event_id)

    def publish_metrics(
        self,
        metrics: TelemetrySnapshot,
        qos: int = 0,
        retained: bool = False,
    ) -> PublishReceipt:
        """Publish a typed telemetry snapshot on the health topic.

        Snapshots are versioned data, not §2 envelope events; QoS defaults
        to 0 (inside the spec's health allowance) and retained stays False
        unless explicitly requested.
        """
        if not self._connected:
            raise TransportError("Publisher is not connected")
        if qos not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {qos!r}")
        _assert_safe_payload(metrics.to_dict())
        topic = build_topic(self._site_id, metrics.camera_id, "health")
        payload = metrics.to_json()
        try:
            self._transport.publish(topic, payload, qos=qos, retained=retained)
        except TransportError:
            self.failed_count += 1
            raise
        except Exception as exc:
            self.failed_count += 1
            raise TransportError(f"MQTT publish failed: {exc}") from exc
        self.published_count += 1
        return PublishReceipt(
            topic=topic,
            qos=qos,
            retained=retained,
            event_id=f"metrics-{metrics.camera_id}-{metrics.captured_at}",
        )

    def publish_fall(
        self,
        event_type: str,
        camera_id: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PublishReceipt:
        """Publish a ``fall.*`` event on the fall topic (QoS 1 default)."""
        event = MqttEvent.create(
            event_type=event_type,
            source=self._source,
            camera_id=camera_id,
            payload=payload,
            **kwargs,
        )
        return self.publish_event(event, "events/fall")

    def publish_camera(
        self,
        event_type: str,
        camera_id: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PublishReceipt:
        """Publish a ``camera.*`` event on the health topic."""
        event = MqttEvent.create(
            event_type=event_type,
            source=self._source,
            camera_id=camera_id,
            payload=payload,
            **kwargs,
        )
        return self.publish_event(event, "health")

    def publish_incident(
        self,
        event_type: str,
        camera_id: str,
        incident_id: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PublishReceipt:
        """Publish an ``incident.*`` lifecycle event on the health topic."""
        event = MqttEvent.create(
            event_type=event_type,
            source=self._source,
            camera_id=camera_id,
            incident_id=incident_id,
            payload=payload,
            **kwargs,
        )
        return self.publish_event(event, "health")

    def publish_agent(
        self,
        event_type: str,
        camera_id: str,
        incident_id: str | None = None,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PublishReceipt:
        """Publish an ``agent.*`` event on the agent topic."""
        event = MqttEvent.create(
            event_type=event_type,
            source=self._source,
            camera_id=camera_id,
            incident_id=incident_id,
            payload=payload,
            **kwargs,
        )
        return self.publish_event(event, "agent")
