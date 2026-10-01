"""Benchmark harness contract tests (P9-001).

All CPU-deterministic: scripted timers, fake predictors, stub torch module.
No GPU, CUDA, weights, network, sleeps, or cameras required.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from eldercare.benchmark.harness import (
    BenchmarkConfig,
    DeterministicFakePredictor,
    RunMetrics,
    StageTimings,
    aggregate_repeats,
    collect_environment,
    generate_frames,
    percentile,
    read_vram_mb,
    report_to_dict,
    run_once,
    summarize,
    sync_device,
    write_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_YAML = REPO_ROOT / "config" / "fall_detection.yaml"


def _config(**overrides) -> BenchmarkConfig:
    params: dict = {"warmup_frames": 5, "measured_frames": 7, "repetitions": 2}
    params.update(overrides)
    return BenchmarkConfig(**params)


class _ScriptTimer:
    """Deterministic monotonic timer recording every call."""

    def __init__(self, step: float = 0.001) -> None:
        self._time = 0.0
        self._step = step
        self.calls = 0

    def __call__(self) -> float:
        self._time += self._step
        self.calls += 1
        return self._time


def test_percentile_math() -> None:
    ordered = [1.0, 2.0, 3.0, 4.0]
    assert percentile(ordered, 0.0) == 1.0
    assert percentile(ordered, 100.0) == 4.0
    assert percentile(ordered, 50.0) == 2.5
    assert percentile(ordered, 25.0) == 1.75
    assert percentile([9.0], 95.0) == 9.0
    with pytest.raises(ValueError):
        percentile([], 50.0)
    with pytest.raises(ValueError):
        percentile(ordered, 101.0)


def test_summarize_shape() -> None:
    summary = summarize([3.0, 1.0, 2.0])
    assert summary["count"] == 3
    assert summary["mean_ms"] == pytest.approx(2.0)
    assert summary["median_ms"] == pytest.approx(2.0)
    assert summary["min_ms"] == 1.0
    assert summary["max_ms"] == 3.0
    with pytest.raises(ValueError):
        summarize([])


def test_warmup_excluded_from_statistics() -> None:
    config = _config()
    predictor = DeterministicFakePredictor()
    frames = generate_frames(config)
    result = run_once(config, predictor, frames, timer=_ScriptTimer())
    assert result.measured_frames == 7
    assert len(result.stages) == 7
    assert predictor.calls == 12


def test_deterministic_input_ordering() -> None:
    config = _config()
    first = generate_frames(config)
    second = generate_frames(config)
    assert len(first) == len(second) == 12
    for left, right in zip(first, second, strict=True):
        assert left.tobytes() == right.tobytes()
    run_a = run_once(config, DeterministicFakePredictor(), first, timer=_ScriptTimer())
    run_b = run_once(config, DeterministicFakePredictor(), second, timer=_ScriptTimer())
    assert run_a.totals_ms() == run_b.totals_ms()


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        BenchmarkConfig(measured_frames=0)
    with pytest.raises(ValueError):
        BenchmarkConfig(warmup_frames=-1)
    with pytest.raises(ValueError):
        BenchmarkConfig(repetitions=0)
    with pytest.raises(ValueError):
        BenchmarkConfig(imgsz=0)
    config = _config()
    with pytest.raises(ValueError):
        run_once(config, DeterministicFakePredictor(), generate_frames(config)[:3])
    import numpy as np

    bad = [np.zeros((10, 10), dtype=np.uint8)]
    with pytest.raises(ValueError):
        run_once(_config(warmup_frames=0, measured_frames=1), DeterministicFakePredictor(), bad)


def test_cuda_unavailable_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=fake_cuda))
    sync = sync_device()
    assert sync.synchronized is False
    assert sync.device_name is None
    vram = read_vram_mb()
    assert vram.allocated_mb is None
    assert vram.reserved_mb is None


def test_cuda_sync_brackets_inference_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    fake_cuda = types.SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda index: "Fake GPU",
        synchronize=lambda: events.append("S"),
        memory_allocated=lambda index: 0,
        memory_reserved=lambda index: 0,
    )
    fake_torch = types.SimpleNamespace(cuda=fake_cuda, version=types.SimpleNamespace(cuda="12.0"))

    def _timer() -> float:
        events.append("T")
        return len(events) * 0.001

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    sync = sync_device()
    assert (sync.device, sync.synchronized, sync.device_name) == ("cuda", True, "Fake GPU")
    events.clear()
    config = _config(warmup_frames=1, measured_frames=1)
    run_once(config, DeterministicFakePredictor(), generate_frames(config), timer=_timer)
    syncs = [i for i, marker in enumerate(events) if marker == "S"]
    assert len(syncs) == 4
    for position in syncs:
        assert events[position - 1] == "T"
        assert events[position + 1] == "T"


def test_report_schema_covers_required_fields(tmp_path: Path) -> None:
    config = _config()
    runs = [
        run_once(
            config, DeterministicFakePredictor(), generate_frames(config), timer=_ScriptTimer()
        )
    ]
    report = report_to_dict(
        config=config,
        runs=runs,
        environment=collect_environment(),
        input_description={"source": "test"},
        predictor_name="fake-deterministic",
        vram_peak_mb=None,
        rss_baseline_mb=None,
        rss_peak_mb=None,
        model_load_ms=None,
    )
    for key in (
        "schema_version",
        "kind",
        "predictor",
        "config",
        "environment",
        "input",
        "warmup_frames",
        "measured_frames",
        "repetitions",
        "aggregate",
        "latency_all_runs_ms",
        "fps",
        "per_stage_mean_ms",
        "inference_latency_synchronized_ms",
        "vram_baseline_mb",
        "vram_peak_mb",
        "rss_baseline_mb",
        "rss_peak_mb",
        "model_load_ms",
        "per_frame_total_ms",
        "units",
    ):
        assert key in report, key
    target = write_artifact(tmp_path / "nested" / "bench.json", report)
    assert json.loads(target.read_text(encoding="utf-8"))["kind"] == "baseline"


def test_repeat_aggregation_math() -> None:
    def _run(fps: float, mean: float) -> RunMetrics:
        stage = StageTimings(
            preprocess_ms=0.1,
            predict_ms=mean - 0.4,
            adapt_ms=0.1,
            track_ms=0.1,
            fsm_ms=0.1,
            total_ms=mean,
        )
        return RunMetrics(measured_frames=1, loop_wall_s=1.0 / fps, fps=fps, stages=(stage,))

    aggregate = aggregate_repeats([_run(10.0, 100.0), _run(20.0, 50.0), _run(30.0, 25.0)])
    assert aggregate["repetitions"] == 3
    assert aggregate["median_fps"] == pytest.approx(20.0)
    assert aggregate["median_p95_ms"] == pytest.approx(50.0)
    assert aggregate["cv_of_run_means"] > 0.0
    with pytest.raises(ValueError):
        aggregate_repeats([])


def test_no_mutation_of_inference_configuration() -> None:
    from eldercare.vision.pose.inference import UltralyticsPosePredictor

    predictor = UltralyticsPosePredictor()
    assert predictor.model_name == "yolo26s-pose.pt"
    assert predictor.device == 0
    assert predictor.imgsz == 640
    before = hashlib.sha256(CONFIG_YAML.read_bytes()).hexdigest()
    config = _config()
    run_once(config, DeterministicFakePredictor(), generate_frames(config), timer=_ScriptTimer())
    assert predictor.model_name == "yolo26s-pose.pt"
    assert predictor.device == 0
    assert predictor.imgsz == 640
    assert hashlib.sha256(CONFIG_YAML.read_bytes()).hexdigest() == before


def test_cli_entrypoint_smoke(tmp_path: Path) -> None:
    script = REPO_ROOT / "benchmarks" / "scripts" / "benchmark_inference.py"
    spec = importlib.util.spec_from_file_location("benchmark_inference", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "p9_001_baseline.json"
    assert (
        module.main(
            [
                "--predictor",
                "fake",
                "--warmup",
                "1",
                "--frames",
                "2",
                "--reps",
                "1",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["predictor"] == "fake-deterministic"
    assert payload["measured_frames"] == 2
