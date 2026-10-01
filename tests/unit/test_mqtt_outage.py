"""Broker outage and recovery drills (P7-005).

All scenarios run on FakeMqttTransport: no broker, network, sleeps, GPU, or
cameras. A fake sleeper records delays so the retry schedule is asserted
without wall-clock waiting.
"""

from __future__ import annotations

import time

import pytest

from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.pipeline_metrics import collect_pipeline_metrics
from eldercare.mqtt.publisher import MqttPublisher
from eldercare.mqtt.resilience import (
    ReconnectPolicy,
    connect_with_retry,
    publish_best_effort,
    publish_metrics_best_effort,
)


def _connected_publisher(**overrides) -> tuple[MqttPublisher, FakeMqttTransport]:
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="test-site", transport=transport, **overrides)
    publisher.connect()
    return publisher, transport


def _fall_event() -> MqttEvent:
    return MqttEvent.create(
        event_type="fall.confirmed",
        camera_id="cam-01",
        incident_id="inc-1",
        payload={"fall_score": 0.87, "track_id": "7"},
    )


def test_best_effort_never_raises_and_reports() -> None:
    publisher, transport = _connected_publisher()
    transport.fail_publish = True
    outcome = publish_best_effort(publisher, _fall_event(), "events/fall")
    assert outcome.delivered is False
    assert "TransportError" in outcome.reason
    assert outcome.event_id
    transport.fail_publish = False
    recovered = publish_best_effort(publisher, _fall_event(), "events/fall")
    assert recovered.delivered is True
    assert recovered.reason == "ok"


def test_best_effort_swallows_unexpected_errors() -> None:
    publisher, _ = _connected_publisher()
    bad = MqttEvent.create(
        event_type="fall.confirmed", camera_id="cam-01", payload={"password": "x"}
    )
    outcome = publish_best_effort(publisher, bad, "events/fall")
    assert outcome.delivered is False
    assert "ValueError" in outcome.reason


def test_best_effort_swallows_foreign_transport_errors() -> None:
    class _Foreign:
        def connect(self) -> None:
            return None

        def publish(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            raise RuntimeError("boom-publish")

        def disconnect(self) -> None:
            return None

    publisher = MqttPublisher(site_id="s", transport=_Foreign())  # type: ignore[arg-type]
    publisher.connect()
    outcome = publish_best_effort(publisher, _fall_event(), "events/fall")
    assert outcome.delivered is False
    assert outcome.reason


def test_detector_outputs_survive_outage() -> None:
    """Simulated incident flow: broker dies mid-incident, detector data intact."""
    publisher, transport = _connected_publisher()
    event = _fall_event()
    before = dict(event.payload)
    transport.fail_publish = True
    outcome = publish_best_effort(publisher, event, "events/fall")
    assert outcome.delivered is False
    assert event.payload == before
    assert event.event_type == "fall.confirmed"
    assert event.camera_id == "cam-01"
    assert event.incident_id == "inc-1"


def test_metrics_best_effort_never_raises() -> None:
    publisher, transport = _connected_publisher()
    transport.fail_publish = True
    metrics = collect_pipeline_metrics("cam-01", captured_at="2026-09-23T12:00:00Z")
    outcome = publish_metrics_best_effort(publisher, metrics)
    assert outcome.delivered is False
    assert outcome.event_id.startswith("metrics-cam-01-")


def test_reconnect_schedule_bounded_exponential() -> None:
    policy = ReconnectPolicy(initial_delay_s=1.0, max_delay_s=30.0, multiplier=2.0, max_attempts=5)
    assert [policy.delay_for(n) for n in (1, 2, 3, 4, 5)] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert policy.delay_for(6) == 0.0
    assert policy.delay_for(0) == 0.0
    capped = ReconnectPolicy(initial_delay_s=20.0, max_delay_s=30.0, max_attempts=3)
    assert capped.delay_for(3) == 30.0


def test_reconnect_policy_rejects_bad_bounds() -> None:
    with pytest.raises(ValueError):
        ReconnectPolicy(initial_delay_s=0.0)
    with pytest.raises(ValueError):
        ReconnectPolicy(multiplier=0.5)
    with pytest.raises(ValueError):
        ReconnectPolicy(max_attempts=-1)


def test_connect_retry_uses_fake_sleeper_without_waiting() -> None:
    transport = FakeMqttTransport()
    transport.fail_connect = True
    publisher = MqttPublisher(site_id="s", transport=transport)
    policy = ReconnectPolicy(initial_delay_s=1.0, max_delay_s=30.0, max_attempts=3)
    slept: list[float] = []
    started = time.monotonic()
    assert connect_with_retry(publisher, policy, sleeper=slept.append) is False
    assert time.monotonic() - started < 5.0
    assert slept == [1.0, 2.0]
    assert transport.connect_calls == 3


def test_connect_retry_recovers() -> None:
    transport = FakeMqttTransport()
    transport.fail_connect = True
    publisher = MqttPublisher(site_id="s", transport=transport)
    policy = ReconnectPolicy(max_attempts=3)
    assert connect_with_retry(publisher, policy, sleeper=lambda _: None) is False
    transport.fail_connect = False
    assert connect_with_retry(publisher, policy, sleeper=lambda _: None) is True
    assert publisher.connected is True


def test_duplicate_delivery_keeps_stable_id_without_storm() -> None:
    publisher, transport = _connected_publisher()
    event = _fall_event()
    first = publish_best_effort(publisher, event, "events/fall")
    second = publish_best_effort(publisher, event, "events/fall")
    assert first.delivered and second.delivered
    assert first.event_id == second.event_id == event.event_id
    assert len(transport.published) == 2, "exactly one transport call per API call"


def test_clean_shutdown_after_failures() -> None:
    publisher, transport = _connected_publisher()
    transport.fail_publish = True
    publish_best_effort(publisher, _fall_event(), "events/fall")
    publisher.disconnect()
    publisher.disconnect()
    assert publisher.connected is False
    assert transport.disconnect_calls >= 2
