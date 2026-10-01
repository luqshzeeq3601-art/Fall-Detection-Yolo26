"""Pipeline telemetry snapshot tests (P7-003).

Uses REAL P1-006 CaptureSnapshot and P2-005 PoseTiming objects as sources:
no fakes for the measured data itself, FakeMqttTransport only for delivery.
No broker, network, sleeps, GPU, or cameras.
"""

from __future__ import annotations

import json

import pytest

from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.pipeline_metrics import (
    SNAPSHOT_SCHEMA_VERSION,
    collect_pipeline_metrics,
    snapshot_topic,
)
from eldercare.mqtt.publisher import MqttPublisher, TransportError
from eldercare.vision.pose.timing import PoseTiming
from eldercare.vision.stream.telemetry import CaptureSnapshot


def _capture(**overrides) -> CaptureSnapshot:
    fields: dict = {
        "camera_id": "cam-01",
        "captured_at": 1000.0,
        "capture_fps": 29.5,
        "frames_received": 60,
        "queue_submitted": 60,
        "queue_dropped": 2,
        "queue_depth": 1,
        "reconnect_attempts": 3,
        "reconnect_failures": 0,
        "health_state": "online",
        "last_frame_at": 999.9,
        "seconds_since_last_frame": 0.1,
    }
    fields.update(overrides)
    return CaptureSnapshot(**fields)


def _timing() -> PoseTiming:
    return PoseTiming(predict_ms=10.0, adapt_ms=2.0, total_ms=12.0)


def test_unknown_sources_stay_unknown() -> None:
    metrics = collect_pipeline_metrics("cam-01", captured_at="2026-09-23T12:00:00Z")
    assert metrics.schema_version == SNAPSHOT_SCHEMA_VERSION == "1.0"
    assert metrics.capture_fps is None
    assert metrics.inference_total_ms is None
    assert metrics.queue_depth is None
    assert metrics.reconnect_attempts is None
    assert metrics.health_state is None
    assert json.loads(metrics.to_json())["capture_fps"] is None


def test_values_flow_from_real_sources() -> None:
    metrics = collect_pipeline_metrics(
        "cam-01", capture=_capture(), timing=_timing(), captured_at="2026-09-23T12:00:00Z"
    )
    assert metrics.capture_fps == 29.5
    assert metrics.inference_predict_ms == 10.0
    assert metrics.inference_adapt_ms == 2.0
    assert metrics.inference_total_ms == 12.0
    assert metrics.queue_submitted == 60
    assert metrics.queue_dropped == 2
    assert metrics.queue_depth == 1
    assert metrics.reconnect_attempts == 3
    assert metrics.reconnect_failures == 0
    assert metrics.health_state == "online"


def test_no_fabrication_from_sparse_capture() -> None:
    sparse = _capture(capture_fps=None, queue_depth=None, health_state=None)
    metrics = collect_pipeline_metrics("cam-01", capture=sparse, timing=None)
    assert metrics.capture_fps is None
    assert metrics.queue_depth is None
    assert metrics.health_state is None
    assert metrics.inference_total_ms is None


def test_serialization_deterministic() -> None:
    kwargs: dict = {
        "capture": _capture(),
        "timing": _timing(),
        "captured_at": "2026-09-23T12:00:00Z",
    }
    first = collect_pipeline_metrics("cam-01", **kwargs).to_json()
    second = collect_pipeline_metrics("cam-01", **kwargs).to_json()
    assert first == second
    assert '"schema_version":"1.0"' in first


def test_empty_camera_id_rejected() -> None:
    with pytest.raises(ValueError):
        collect_pipeline_metrics("")


def test_snapshot_topic_is_health() -> None:
    assert snapshot_topic("site-a", "cam-01") == "eldercare/site-a/cam-01/health"


def test_publish_metrics_wiring() -> None:
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="site-a", transport=transport)
    publisher.connect()
    metrics = collect_pipeline_metrics(
        "cam-01", capture=_capture(), timing=_timing(), captured_at="2026-09-23T12:00:00Z"
    )
    receipt = publisher.publish_metrics(metrics)
    assert receipt.topic == "eldercare/site-a/cam-01/health"
    assert receipt.qos == 0
    assert receipt.retained is False
    assert len(transport.published) == 1
    body = json.loads(transport.published[0].payload)
    assert body["schema_version"] == "1.0"
    assert body["inference_total_ms"] == 12.0


def test_publish_metrics_requires_connection() -> None:
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="site-a", transport=transport)
    metrics = collect_pipeline_metrics("cam-01")
    with pytest.raises(TransportError):
        publisher.publish_metrics(metrics)
