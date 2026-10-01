"""Topic, envelope, and publisher contract tests for versioned MQTT (P7-002).

Deterministic unit tests over FakeMqttTransport: no broker, network, sleeps,
GPU, or cameras. Covers EVENT_SCHEMA.md §§1/2/4/5 requirements.
"""

from __future__ import annotations

import json

import pytest

from eldercare.mqtt.envelope import MqttEvent
from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.publisher import MqttPublisher, TransportError
from eldercare.mqtt.topics import SCHEMA_VERSION, build_topic


def _publisher(**overrides) -> tuple[MqttPublisher, FakeMqttTransport]:
    transport = FakeMqttTransport()
    params = {"site_id": "test-site", "transport": transport}
    params.update(overrides)
    publisher = MqttPublisher(**params)  # type: ignore[arg-type]
    publisher.connect()
    assert transport.connected
    return publisher, transport


def test_topic_roots_match_event_schema() -> None:
    assert build_topic("site-a", "cam-01", "events/fall") == "eldercare/site-a/cam-01/events/fall"
    assert build_topic("site-a", "cam-01", "health") == "eldercare/site-a/cam-01/health"
    assert build_topic("site-a", "cam-01", "agent") == "eldercare/site-a/cam-01/agent"


@pytest.mark.parametrize("bad", ["", "cam/01", "cam 01", "cam+01", "cam#01", "cam\n01"])
def test_topic_segments_reject_wildcards_and_separators(bad: str) -> None:
    with pytest.raises(ValueError):
        build_topic(bad, "cam-01", "health")
    with pytest.raises(ValueError):
        build_topic("site-a", bad, "health")


def test_unknown_category_rejected() -> None:
    with pytest.raises(ValueError):
        build_topic("site-a", "cam-01", "video")  # type: ignore[arg-type]


def test_envelope_carries_schema_version_and_utc_stamp() -> None:
    event = MqttEvent.create(event_type="fall.confirmed", camera_id="cam-01")
    assert event.schema_version == SCHEMA_VERSION == "1.0"
    assert event.source == "vision-service"
    assert event.occurred_at.endswith("Z")


def test_serialization_is_deterministic() -> None:
    kwargs = {
        "event_type": "fall.confirmed",
        "camera_id": "cam-01",
        "event_id": "fixed-id",
        "occurred_at": "2026-09-23T12:00:00Z",
        "payload": {"b": 2, "a": 1},
    }
    first = MqttEvent.create(**kwargs).to_json()  # type: ignore[arg-type]
    second = MqttEvent.create(**kwargs).to_json()  # type: ignore[arg-type]
    assert first == second
    assert json.loads(first)["payload"] == {"a": 1, "b": 2}


def test_nan_payload_rejected() -> None:
    event = MqttEvent.create(event_type="fall.confirmed", payload={"score": float("nan")})
    with pytest.raises(ValueError):
        event.to_json()


def test_from_json_round_trip_ignores_additive_fields() -> None:
    event = MqttEvent.create(event_type="camera.online", camera_id="cam-01")
    raw = event.to_json()
    data = json.loads(raw)
    data["brand_new_field"] = "future"
    parsed = MqttEvent.from_json(json.dumps(data))
    assert parsed == event


def _envelope_raw(occurred_at: str) -> str:
    return json.dumps(
        {
            "event_id": "e-1",
            "event_type": "fall.confirmed",
            "schema_version": "1.0",
            "occurred_at": occurred_at,
            "source": "vision-service",
            "camera_id": "cam-01",
            "incident_id": None,
            "payload": {},
        }
    )


def test_from_json_accepts_utc_and_offset_stamps() -> None:
    assert MqttEvent.from_json(_envelope_raw("2026-09-23T12:00:00Z")).occurred_at.endswith("Z")
    parsed = MqttEvent.from_json(_envelope_raw("2026-09-23T12:00:00+00:00"))
    assert parsed.occurred_at.endswith("+00:00")


@pytest.mark.parametrize(
    "bad_stamp", ["yesterday", "2026-13-99", "12:00:00", "2026-09-23T12:00:00"]
)
def test_from_json_rejects_non_iso_or_naive_stamps(bad_stamp: str) -> None:
    """REL-001 regression: malformed timestamps fail closed like create()."""
    with pytest.raises(ValueError):
        MqttEvent.from_json(_envelope_raw(bad_stamp))


@pytest.mark.parametrize(
    "raw",
    ["not-json", "[]", "{}", '{"event_id": "x"}', '{"event_id":"a","event_type":"t"}'],
)
def test_from_json_rejects_malformed(raw: str) -> None:
    with pytest.raises(ValueError):
        MqttEvent.from_json(raw)


def test_qos_defaults_match_spec() -> None:
    publisher, transport = _publisher()
    publisher.publish_fall("fall.confirmed", "cam-01", {"fall_score": 0.87})
    publisher.publish_camera("camera.offline", "cam-02")
    publisher.publish_agent("agent.enrichment_completed", "cam-01", incident_id="inc-1")
    by_topic = {record.topic: record for record in transport.published}
    assert by_topic["eldercare/test-site/cam-01/events/fall"].qos == 1
    assert by_topic["eldercare/test-site/cam-02/health"].qos == 1
    assert by_topic["eldercare/test-site/cam-01/agent"].qos == 1
    assert all(record.retained is False for record in transport.published)


def test_incident_events_route_to_health_topic() -> None:
    publisher, transport = _publisher()
    receipt = publisher.publish_incident("incident.persisted", "cam-01", "inc-9")
    assert receipt.topic == "eldercare/test-site/cam-01/health"
    assert receipt.event_id


def test_explicit_qos_override_and_invalid_qos() -> None:
    publisher, transport = _publisher()
    event = MqttEvent.create(event_type="camera.online", camera_id="cam-01")
    receipt = publisher.publish_event(event, "health", qos=0)
    assert receipt.qos == 0
    with pytest.raises(ValueError):
        publisher.publish_event(event, "health", qos=5)


@pytest.mark.parametrize(
    "payload",
    [
        {"rtsp_url": "rtsp://x"},
        {"nested": {"password": "p"}},
        {"nested": {"deep": {"token": "t"}}},
        {"STACK_TRACE": "..."},
    ],
)
def test_sensitive_payload_keys_rejected(payload: dict) -> None:
    publisher, _ = _publisher()
    event = MqttEvent.create(event_type="fall.confirmed", camera_id="cam-01", payload=payload)
    with pytest.raises(ValueError):
        publisher.publish_event(event, "events/fall")


def test_publish_requires_connection() -> None:
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="s", transport=transport)
    event = MqttEvent.create(event_type="fall.confirmed", camera_id="cam-01")
    with pytest.raises(TransportError):
        publisher.publish_event(event, "events/fall")


def test_transport_failure_counts_and_disconnect_is_safe() -> None:
    publisher, transport = _publisher()
    transport.fail_publish = True
    event = MqttEvent.create(event_type="fall.confirmed", camera_id="cam-01")
    with pytest.raises(TransportError):
        publisher.publish_event(event, "events/fall")
    assert publisher.failed_count == 1
    assert publisher.published_count == 0
    publisher.disconnect()
    publisher.disconnect()
    assert publisher.connected is False


def test_counters_track_success() -> None:
    publisher, _ = _publisher()
    publisher.publish_camera("camera.online", "cam-01")
    publisher.publish_camera("camera.online", "cam-01")
    assert publisher.published_count == 2
    assert publisher.failed_count == 0


def test_settings_site_id_default_and_plain_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    from eldercare.common.settings import Settings

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.delenv("MQTT_SITE_ID", raising=False)
    settings = Settings()
    assert settings.MQTT_SITE_ID == "local-site"
    assert settings.redacted_summary()["MQTT_SITE_ID"] == "local-site"
