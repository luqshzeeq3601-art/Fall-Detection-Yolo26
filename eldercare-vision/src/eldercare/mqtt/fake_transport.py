"""Deterministic fake MQTT transport for unit tests (P7-002).

Test/demo only: records publishes in memory and replays scripted failures
so publisher, metrics, and outage behavior stay deterministic without a live
broker, network, sleeps, GPU, or cameras.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecordedPublish:
    """One publish call observed by the fake transport."""

    topic: str
    payload: str
    qos: int
    retained: bool


@dataclass
class FakeMqttTransport:
    """In-memory transport implementing the publisher's protocol."""

    connected: bool = False
    fail_connect: bool = False
    fail_publish: bool = False
    published: list[RecordedPublish] = field(default_factory=list)
    connect_calls: int = 0
    disconnect_calls: int = 0

    def connect(self) -> None:
        """Pretend to open a broker connection (or fail as scripted)."""
        from eldercare.mqtt.publisher import TransportError

        self.connect_calls += 1
        if self.fail_connect:
            raise TransportError("Fake broker refused the connection")
        self.connected = True

    def publish(self, topic: str, payload: str, qos: int = 0, retained: bool = False) -> None:
        """Record a publish (or fail as scripted)."""
        from eldercare.mqtt.publisher import TransportError

        if not self.connected:
            raise TransportError("Fake transport is not connected")
        if self.fail_publish:
            raise TransportError("Fake broker rejected the publish")
        self.published.append(
            RecordedPublish(topic=topic, payload=payload, qos=qos, retained=retained)
        )

    def disconnect(self) -> None:
        """Pretend to close the broker connection."""
        self.disconnect_calls += 1
        self.connected = False
