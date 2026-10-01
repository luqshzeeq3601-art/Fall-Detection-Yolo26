"""Host telemetry collection tests (P7-004).

Deterministic without hardware: meminfo fixtures, monkeypatched OS readers,
and a stub torch module. No sleeps, broker, network, GPU, or cameras.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from eldercare.mqtt.fake_transport import FakeMqttTransport
from eldercare.mqtt.host_telemetry import (
    HOST_SCHEMA_VERSION,
    collect_host_telemetry,
    parse_meminfo,
    read_cpu_count,
    read_cuda,
    read_loadavg,
)
from eldercare.mqtt.publisher import MqttPublisher

_MEMINFO = """\
MemTotal:        8021052 kB
MemFree:         1024000 kB
MemAvailable:    4010224 kB
Buffers:          123456 kB
"""


def test_parse_meminfo_converts_kb_to_mb() -> None:
    total, available = parse_meminfo(_MEMINFO)
    assert total == pytest.approx(8021052 / 1024.0)
    assert available == pytest.approx(4010224 / 1024.0)


def test_parse_meminfo_missing_fields_stay_unknown() -> None:
    assert parse_meminfo("MemTotal: 100 kB\n") == (None, None)
    assert parse_meminfo("garbage") == (None, None)


def test_cpu_count_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert read_cpu_count() == 8
    monkeypatch.setattr(os, "cpu_count", lambda: 0)
    assert read_cpu_count() is None
    monkeypatch.setattr(os, "cpu_count", lambda: (_ for _ in ()).throw(OSError("no")))
    assert read_cpu_count() is None


def test_loadavg_absent_platform_stays_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)
    assert read_loadavg() == (None, None, None)
    monkeypatch.setattr(os, "getloadavg", lambda: (1.5, 0.75, 0.25), raising=False)
    assert read_loadavg() == (1.5, 0.75, 0.25)


def test_cuda_absent_means_cpu_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setitem(sys.modules, "torch", None)
    device, name, allocated, total = read_cuda()
    assert device == "cpu"
    assert name is None
    assert allocated is None
    assert total is None


def test_cuda_present_reports_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    fake = types.ModuleType("torch")

    class _Props:
        total_memory = 8 * 1024 * 1024 * 1024

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def get_device_name(index: int) -> str:
            assert index == 0
            return "NVIDIA GeForce RTX 3070"

        @staticmethod
        def get_device_properties(index: int) -> _Props:
            assert index == 0
            return _Props()

        @staticmethod
        def memory_allocated(index: int) -> int:
            assert index == 0
            return 512 * 1024 * 1024

    fake.cuda = _Cuda  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake)
    device, name, allocated, total = read_cuda()
    assert device == "cuda:0"
    assert name == "NVIDIA GeForce RTX 3070"
    assert allocated == pytest.approx(512.0)
    assert total == pytest.approx(8192.0)


def test_collect_never_raises_and_marks_schema(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setitem(sys.modules, "torch", None)
    telemetry = collect_host_telemetry("cam-01", captured_at="2026-09-23T12:00:00Z")
    assert telemetry.schema_version == HOST_SCHEMA_VERSION == "1.0"
    assert telemetry.camera_id == "cam-01"
    body = json.loads(telemetry.to_json())
    assert body["gpu_device"] == "cpu"
    assert telemetry.to_json() == telemetry.to_json()


def test_empty_camera_id_rejected() -> None:
    with pytest.raises(ValueError):
        collect_host_telemetry("")


def test_publish_host_telemetry_wiring() -> None:
    transport = FakeMqttTransport()
    publisher = MqttPublisher(site_id="site-a", transport=transport)
    publisher.connect()
    telemetry = collect_host_telemetry("cam-01", captured_at="2026-09-23T12:00:00Z")
    receipt = publisher.publish_metrics(telemetry)
    assert receipt.topic == "eldercare/site-a/cam-01/health"
    assert receipt.qos == 0
    assert receipt.retained is False
    body = json.loads(transport.published[0].payload)
    assert body["schema_version"] == "1.0"
    assert "cpu_count" in body
