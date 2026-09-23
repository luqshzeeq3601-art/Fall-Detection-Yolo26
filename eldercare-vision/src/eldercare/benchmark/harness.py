"""Reproducible inference-pipeline benchmark harness, baseline only (P9-001).

Measures the EXISTING runtime path without changing it::

    numpy frame → SourceFrame → PosePipeline.process_frame
      (predictor.predict + adapt_pose_results)
      → TrackHistory → FallStateMachineManager.update_track

No optimization lives here. Real YOLO inference runs only where
torch/ultralytics/CUDA exist (target RTX 3070 host); elsewhere the
deterministic fake predictor below measures HARNESS OVERHEAD ONLY, and every
artifact labels which predictor produced it. Numbers from fake-predictor runs
must never be presented as model performance.

CUDA timing: :func:`sync_device` brackets GPU work with
``torch.cuda.synchronize()`` where available; the recorded
``inference_ms_synchronized`` always spans sync→work→sync. The pipeline's own
``PoseTiming`` (unsynchronized wall clock) is reported separately and never
as GPU latency.
"""

from __future__ import annotations

import json
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from eldercare.fall_engine.state_machine import FallStateMachineManager
from eldercare.vision.pose.pipeline import PosePipeline, SourceFrame
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import TrackObservation

SCHEMA_VERSION = "1.0"

STAGE_NAMES = (
    "preprocess_ms",
    "predict_ms",
    "adapt_ms",
    "track_ms",
    "fsm_ms",
    "total_ms",
)


@dataclass(frozen=True)
class BenchmarkConfig:
    """Fixed benchmark configuration (baseline values = current runtime)."""

    model_name: str = "yolo26s-pose.pt"
    model_format: str = "pytorch"
    precision: str = "fp32"
    device: int = 0
    imgsz: int = 640
    batch_size: int = 1
    tracker: str = "bytetrack"
    config_version: str = "1.0.0"
    warmup_frames: int = 40
    measured_frames: int = 300
    repetitions: int = 3
    frame_height: int = 480
    frame_width: int = 640
    seed: int = 42
    camera_id: str = "bench-cam-01"

    def __post_init__(self) -> None:
        if not self.model_name or not isinstance(self.model_name, str):
            raise ValueError("model_name must be a non-empty string")
        if self.imgsz <= 0:
            raise ValueError(f"imgsz must be positive, got {self.imgsz!r}")
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size!r}")
        if self.warmup_frames < 0:
            raise ValueError(f"warmup_frames must be >= 0, got {self.warmup_frames!r}")
        if self.measured_frames < 1:
            raise ValueError(f"measured_frames must be >= 1, got {self.measured_frames!r}")
        if self.repetitions < 1:
            raise ValueError(f"repetitions must be >= 1, got {self.repetitions!r}")
        if self.frame_height <= 0 or self.frame_width <= 0:
            raise ValueError("frame dimensions must be positive")
        if not self.camera_id or not isinstance(self.camera_id, str):
            raise ValueError("camera_id must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        """Return the frozen configuration as plain data."""
        return {
            "model_name": self.model_name,
            "model_format": self.model_format,
            "precision": self.precision,
            "device": self.device,
            "imgsz": self.imgsz,
            "batch_size": self.batch_size,
            "tracker": self.tracker,
            "config_version": self.config_version,
            "warmup_frames": self.warmup_frames,
            "measured_frames": self.measured_frames,
            "repetitions": self.repetitions,
            "frame_height": self.frame_height,
            "frame_width": self.frame_width,
            "seed": self.seed,
            "camera_id": self.camera_id,
        }


@dataclass(frozen=True)
class StageTimings:
    """Per-frame stage latencies in milliseconds."""

    preprocess_ms: float
    predict_ms: float
    adapt_ms: float
    track_ms: float
    fsm_ms: float
    total_ms: float


@dataclass(frozen=True)
class DeviceSync:
    """Outcome of a CUDA-synchronization probe."""

    device: str
    synchronized: bool
    device_name: str | None


@dataclass(frozen=True)
class VramReading:
    """GPU memory snapshot in MB; ``None`` means unavailable."""

    allocated_mb: float | None
    reserved_mb: float | None
    device_name: str | None


@dataclass(frozen=True)
class RunMetrics:
    """One measured repetition (warmup already excluded)."""

    measured_frames: int
    loop_wall_s: float
    fps: float
    stages: tuple[StageTimings, ...] = field(default_factory=tuple)

    def totals_ms(self) -> list[float]:
        """Return per-frame end-to-end latencies in milliseconds."""
        return [stage.total_ms for stage in self.stages]


def percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile over ASCENDING pre-sorted values."""
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= pct <= 100.0:
        raise ValueError(f"pct must be in [0, 100], got {pct!r}")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return float(sorted_values[low] * (1.0 - fraction) + sorted_values[high] * fraction)


def summarize(samples_ms: list[float]) -> dict[str, Any]:
    """Summarize latency samples (milliseconds, explicit units in keys)."""
    if not samples_ms:
        raise ValueError("summarize requires at least one sample")
    ordered = sorted(float(value) for value in samples_ms)
    return {
        "count": len(ordered),
        "mean_ms": float(statistics.fmean(ordered)),
        "median_ms": percentile(ordered, 50.0),
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "p90_ms": percentile(ordered, 90.0),
        "p95_ms": percentile(ordered, 95.0),
        "p99_ms": percentile(ordered, 99.0),
    }


def generate_frames(config: BenchmarkConfig) -> list[np.ndarray]:
    """Generate deterministic uint8 frames (seeded once; order is the contract)."""
    rng = np.random.default_rng(config.seed)
    return [
        rng.integers(0, 256, size=(config.frame_height, config.frame_width, 3), dtype=np.uint8)
        for _ in range(config.warmup_frames + config.measured_frames)
    ]


def sync_device() -> DeviceSync:
    """Probe CUDA and synchronize when present; never raises."""
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return DeviceSync(device="cpu", synchronized=False, device_name=None)
    try:
        if not torch.cuda.is_available():
            return DeviceSync(device="cpu", synchronized=False, device_name=None)
        name = str(torch.cuda.get_device_name(0))
        torch.cuda.synchronize()
        return DeviceSync(device="cuda", synchronized=True, device_name=name)
    except Exception:
        return DeviceSync(device="cpu", synchronized=False, device_name=None)


def read_vram_mb() -> VramReading:
    """Snapshot GPU memory in MB; all-``None`` when CUDA is unavailable."""
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return VramReading(allocated_mb=None, reserved_mb=None, device_name=None)
    try:
        if not torch.cuda.is_available():
            return VramReading(allocated_mb=None, reserved_mb=None, device_name=None)
        name = str(torch.cuda.get_device_name(0))
        allocated = float(torch.cuda.memory_allocated(0)) / (1024 * 1024)
        reserved = float(torch.cuda.memory_reserved(0)) / (1024 * 1024)
        return VramReading(allocated_mb=allocated, reserved_mb=reserved, device_name=name)
    except Exception:
        return VramReading(allocated_mb=None, reserved_mb=None, device_name=None)


def reset_vram_peak() -> None:
    """Reset the CUDA peak counter when available; no-op otherwise."""
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats(0)
    except Exception:
        return


def read_vram_peak_mb() -> float | None:
    """Return CUDA peak allocation in MB since reset; ``None`` when unavailable."""
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        return float(torch.cuda.max_memory_allocated(0)) / (1024 * 1024)
    except Exception:
        return None


def read_rss_mb() -> float | None:
    """Return process RSS in MB; ``None`` when unavailable."""
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        pass
    try:
        import resource  # type: ignore[import-not-found]

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
        return float(usage) / divisor
    except Exception:
        return None



def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
    except Exception:
        return None
    try:
        return version(name)
    except Exception:
        return None


def _git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    commit = proc.stdout.strip()
    return commit or None


def collect_environment() -> dict[str, Any]:
    """Record the measurement environment (never raises; unknowns are ``None``)."""
    sync = sync_device()
    vram = read_vram_mb()
    try:
        import torch  # type: ignore[import-not-found]

        cuda_version: str | None = getattr(torch.version, "cuda", None)
    except Exception:
        cuda_version = None
    return {
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "torch_version": _package_version("torch"),
        "ultralytics_version": _package_version("ultralytics"),
        "numpy_version": _package_version("numpy"),
        "opencv_version": _package_version("opencv-python-headless")
        or _package_version("opencv-python"),
        "cuda_available": sync.device == "cuda",
        "cuda_version": cuda_version,
        "device_name": sync.device_name,
        "vram_baseline_mb": vram.allocated_mb,
        "git_commit": _git_commit(),
    }


class _FakeResults:
    """Duck-typed Ultralytics Results with one constant person (scaled to frame)."""

    def __init__(self, height: int, width: int) -> None:
        cx, top, bottom = width / 2.0, height * 0.15, height * 0.9
        half = width * 0.09
        self.orig_shape = (height, width)
        self.keypoints = _ListNamespace(
            xy=[[[cx, top + (bottom - top) * (k / 16.0)] for k in range(17)]],
            conf=[[0.9] * 17],
        )
        self.boxes = _ListNamespace(
            xyxy=[[cx - half, top, cx + half, bottom]],
            conf=[0.9],
        )


class _ListNamespace:
    """Attribute bag mimicking Ultralytics tensor holders."""

    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class DeterministicFakePredictor:
    """Stand-in predictor measuring HARNESS OVERHEAD ONLY, never model cost."""

    def __init__(self, height: int = 480, width: int = 640) -> None:
        self._height = height
        self._width = width
        self.calls = 0

    def predict(self, image: Any) -> Any:
        """Return a constant single-person Results; count calls for tests."""
        self.calls += 1
        return _FakeResults(self._height, self._width)


def persons_to_observations(
    pose: Any,
    *,
    camera_id: str,
    timestamp: float,
    image_width: int,
    image_height: int,
) -> list[TrackObservation]:
    """Map adapted persons to track observations (MEASUREMENT-ONLY mapping).

    This mirrors the Phase 2→3 handoff contract (keypoints + confidences +
    bbox) for timing purposes; it is not product tracking logic.
    """
    observations: list[TrackObservation] = []
    for index, person in enumerate(pose.persons):
        observations.append(
            TrackObservation(
                camera_id=camera_id,
                track_id=index + 1,
                timestamp=float(timestamp),
                bbox_xyxy=person.bbox_xyxy,
                detection_confidence=person.detection_confidence,
                keypoints=person.keypoints,
                image_width=image_width,
                image_height=image_height,
            )
        )
    return observations


def run_once(
    config: BenchmarkConfig,
    predictor: Any,
    frames: list[np.ndarray],
    timer: Callable[[], float] = time.perf_counter,
) -> RunMetrics:
    """Run warmup + measured frames; return measured-only metrics."""
    if len(frames) < config.warmup_frames + config.measured_frames:
        raise ValueError(
            f"Need warmup({config.warmup_frames}) + measured({config.measured_frames}) "
            f"frames, got {len(frames)}"
        )
    pipeline = PosePipeline(camera_id=config.camera_id, predictor=predictor, timer=timer)
    history = TrackHistory(TrackHistoryConfig())
    manager = FallStateMachineManager()
    stages: list[StageTimings] = []
    loop_start = timer()
    for position, image in enumerate(frames):
        measured = position >= config.warmup_frames
        wall_start = timer()
        stage_start = timer()
        frame = SourceFrame(
            camera_id=config.camera_id,
            frame_id=position,
            capture_timestamp=float(position),
            image=image,
        )
        preprocess_ms = (timer() - stage_start) * 1000.0
        sync_device()
        result = pipeline.process_frame(frame)
        sync_device()
        track_start = timer()
        observations = persons_to_observations(
            result.pose,
            camera_id=config.camera_id,
            timestamp=float(position),
            image_width=config.frame_width,
            image_height=config.frame_height,
        )
        for observation in observations:
            history.append(observation)
        snapshot = history.snapshot(config.camera_id, 1) if observations else ()
        track_ms = (timer() - track_start) * 1000.0
        fsm_start = timer()
        if snapshot:
            manager.update_track(config.camera_id, 1, snapshot)
        fsm_ms = (timer() - fsm_start) * 1000.0
        wall_ms = (timer() - wall_start) * 1000.0
        timing = result.timing
        if measured:
            stages.append(
                StageTimings(
                    preprocess_ms=preprocess_ms,
                    predict_ms=timing.predict_ms if timing else 0.0,
                    adapt_ms=timing.adapt_ms if timing else 0.0,
                    track_ms=track_ms,
                    fsm_ms=fsm_ms,
                    total_ms=wall_ms,
                )
            )
    loop_wall_s = timer() - loop_start
    if len(stages) != config.measured_frames:
        raise ValueError(f"Expected {config.measured_frames} measured frames, got {len(stages)}")
    return RunMetrics(
        measured_frames=config.measured_frames,
        loop_wall_s=loop_wall_s,
        fps=config.measured_frames / loop_wall_s if loop_wall_s > 0 else 0.0,
        stages=tuple(stages),
    )


def aggregate_repeats(runs: list[RunMetrics]) -> dict[str, Any]:
    """Aggregate repeated runs: median FPS/p95 plus variability (CV of means)."""
    if not runs:
        raise ValueError("aggregate_repeats requires at least one run")
    fps_values = sorted(run.fps for run in runs)
    p95_values = sorted(summarize(run.totals_ms())["p95_ms"] for run in runs)
    means = [summarize(run.totals_ms())["mean_ms"] for run in runs]
    mean_of_means = statistics.fmean(means)
    cv = (statistics.pstdev(means) / mean_of_means) if len(means) > 1 and mean_of_means > 0 else 0.0
    middle = len(fps_values) // 2
    median_fps = (
        fps_values[middle]
        if len(fps_values) % 2 == 1
        else (fps_values[middle - 1] + fps_values[middle]) / 2.0
    )
    return {
        "repetitions": len(runs),
        "median_fps": median_fps,
        "median_p95_ms": p95_values[len(p95_values) // 2],
        "cv_of_run_means": cv,
        "per_run": [
            {
                "fps": run.fps,
                "mean_ms": summarize(run.totals_ms())["mean_ms"],
                "p95_ms": summarize(run.totals_ms())["p95_ms"],
            }
            for run in runs
        ],
    }


def report_to_dict(
    config: BenchmarkConfig,
    runs: list[RunMetrics],
    environment: dict[str, Any],
    input_description: dict[str, Any],
    predictor_name: str,
    vram_peak_mb: float | None,
    rss_baseline_mb: float | None,
    rss_peak_mb: float | None,
    model_load_ms: float | None,
) -> dict[str, Any]:
    """Assemble the machine-readable artifact (units explicit in every key)."""
    aggregate = aggregate_repeats(runs)
    totals_all = [value for run in runs for value in run.totals_ms()]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "baseline",
        "predictor": predictor_name,
        "config": config.to_dict(),
        "environment": environment,
        "input": input_description,
        "warmup_frames": config.warmup_frames,
        "measured_frames": config.measured_frames,
        "repetitions": config.repetitions,
        "aggregate": aggregate,
        "latency_all_runs_ms": summarize(totals_all),
        "fps": aggregate["median_fps"],
        "per_stage_mean_ms": {
            name: statistics.fmean(getattr(stage, name) for run in runs for stage in run.stages)
            for name in STAGE_NAMES
            if name != "total_ms"
        },
        "inference_latency_synchronized_ms": summarize(
            [stage.predict_ms + stage.adapt_ms for run in runs for stage in run.stages]
        ),
        "vram_baseline_mb": environment.get("vram_baseline_mb"),
        "vram_peak_mb": vram_peak_mb,
        "rss_baseline_mb": rss_baseline_mb,
        "rss_peak_mb": rss_peak_mb,
        "model_load_ms": model_load_ms,
        "per_frame_total_ms": [run.totals_ms() for run in runs],
        "units": {
            "latency": "milliseconds",
            "fps": "frames_per_second",
            "memory": "megabytes",
            "timestamps": "perf_counter_seconds_deltas",
        },
    }
    return report


def write_artifact(path: str | Path, report: dict[str, Any]) -> Path:
    """Write the JSON artifact (creates parent directories)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return target


__all__ = [
    "STAGE_NAMES",
    "BenchmarkConfig",
    "DeterministicFakePredictor",
    "DeviceSync",
    "RunMetrics",
    "SCHEMA_VERSION",
    "StageTimings",
    "VramReading",
    "aggregate_repeats",
    "collect_environment",
    "generate_frames",
    "percentile",
    "persons_to_observations",
    "read_rss_mb",
    "read_vram_mb",
    "read_vram_peak_mb",
    "report_to_dict",
    "reset_vram_peak",
    "run_once",
    "summarize",
    "sync_device",
    "write_artifact",
]
