"""Broker outage and recovery behavior for ElderCare Vision (P7-005).

Core guarantee (ARCHITECTURE.md §7): an MQTT outage must NEVER break the
deterministic fall detector or the persistence path. Every helper here is
best-effort and non-raising toward its caller; failures surface as data
(:class:`PublishOutcome`, ``False`` returns), never as exceptions.

Duplicate delivery: QoS 1 is at-least-once, so a retried publish may arrive
twice. Retries always resend the SAME :class:`MqttEvent` (stable
``event_id``), letting consumers dedupe; this module never loops publishes
(one transport call per API call) and never re-subscribes anything (the
publisher holds no subscriptions).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.publisher import MqttPublisher, TelemetrySnapshot, TopicCategory


@dataclass(frozen=True)
class PublishOutcome:
    """Result of a best-effort publish; failures are data, not exceptions."""

    delivered: bool
    reason: str
    topic: str
    event_id: str


@dataclass(frozen=True)
class ReconnectPolicy:
    """Bounded exponential-backoff schedule (pure computation, no sleeping).

    ``delay_for(attempt)`` with 1-based ``attempt`` returns seconds to wait
    before that attempt, capped at ``max_delay_s``. Attempts beyond
    ``max_attempts`` return ``0.0`` (caller stops — no busy loop).
    """

    initial_delay_s: float = 1.0
    max_delay_s: float = 30.0
    multiplier: float = 2.0
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if not self.initial_delay_s > 0:
            raise ValueError("initial_delay_s must be positive")
        if not self.max_delay_s > 0:
            raise ValueError("max_delay_s must be positive")
        if not self.multiplier >= 1.0:
            raise ValueError("multiplier must be >= 1.0")
        if not isinstance(self.max_attempts, int) or self.max_attempts < 0:
            raise ValueError("max_attempts must be a non-negative integer")

    def delay_for(self, attempt: int) -> float:
        """Return the wait before 1-based ``attempt`` (0.0 = budget spent)."""
        if not isinstance(attempt, int) or attempt < 1 or attempt > self.max_attempts:
            return 0.0
        delay = self.initial_delay_s * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_delay_s)


def publish_best_effort(
    publisher: MqttPublisher,
    event: MqttEvent,
    category: TopicCategory,
    qos: int | None = None,
    retained: bool = False,
) -> PublishOutcome:
    """Publish one event without ever raising to the caller."""
    try:
        receipt = publisher.publish_event(event, category, qos=qos, retained=retained)
    except Exception as exc:
        return PublishOutcome(
            delivered=False,
            reason=f"{type(exc).__name__}: {exc}",
            topic="",
            event_id=event.event_id,
        )
    return PublishOutcome(
        delivered=True, reason="ok", topic=receipt.topic, event_id=receipt.event_id
    )


def publish_metrics_best_effort(
    publisher: MqttPublisher,
    metrics: TelemetrySnapshot,
    qos: int = 0,
    retained: bool = False,
) -> PublishOutcome:
    """Publish one telemetry snapshot without ever raising to the caller."""
    try:
        receipt = publisher.publish_metrics(metrics, qos=qos, retained=retained)
    except Exception as exc:
        return PublishOutcome(
            delivered=False,
            reason=f"{type(exc).__name__}: {exc}",
            topic="",
            event_id=f"metrics-{metrics.camera_id}-{metrics.captured_at}",
        )
    return PublishOutcome(
        delivered=True, reason="ok", topic=receipt.topic, event_id=receipt.event_id
    )


def connect_with_retry(
    publisher: MqttPublisher,
    policy: ReconnectPolicy | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Connect with bounded retries; ``True`` on success, ``False`` on exhaustion.

    ``sleeper`` is injectable so tests use a fake (no real sleeps in unit
    CI). Disconnects before each retry so no duplicate transport sessions
    accumulate.
    """
    active = policy or ReconnectPolicy()
    for attempt in range(1, active.max_attempts + 1):
        publisher.disconnect()
        try:
            publisher.connect()
        except Exception:
            if attempt >= active.max_attempts:
                return False
            sleeper(active.delay_for(attempt))
            continue
        return True
    return False


__all__ = [
    "PublishOutcome",
    "ReconnectPolicy",
    "connect_with_retry",
    "publish_best_effort",
    "publish_metrics_best_effort",
]
