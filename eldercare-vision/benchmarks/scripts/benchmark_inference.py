"""Reproducible inference-pipeline baseline benchmark (P9-001).

Baseline only: measures the existing runtime path with zero optimization.
Real YOLO inference requires torch/ultralytics/CUDA (target RTX 3070 host);
elsewhere use `--predictor fake`, which measures HARNESS OVERHEAD ONLY and is
labeled as such in the artifact — never model performance.

Example (target host):
    python benchmarks/scripts/benchmark_inference.py --predictor ultralytics \\
        --warmup 40 --frames 300 --reps 3 --out benchmarks/results/p9_001_baseline.json
"""

# ruff: noqa: T201 - stdout is this script's CLI summary interface (machine
# record lives in the JSON artifact; same waiver pattern as scripts/dev).

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eldercare.benchmark.harness import (  # noqa: E402
    BenchmarkConfig,
    DeterministicFakePredictor,
    collect_environment,
    generate_frames,
    read_rss_mb,
    read_vram_peak_mb,
    report_to_dict,
    reset_vram_peak,
    run_once,
    write_artifact,
)


def build_predictor(kind: str, config: BenchmarkConfig) -> tuple[Any, str, float | None]:
    """Construct the predictor; return (predictor, label, load_ms)."""
    if kind == "fake":
        return (
            DeterministicFakePredictor(height=config.frame_height, width=config.frame_width),
            "fake-deterministic",
            None,
        )
    if kind in ("ultralytics", "pytorch", "onnx", "tensorrt"):
        from eldercare.vision.pose.inference import UltralyticsPosePredictor

        start = time.perf_counter()
        predictor = UltralyticsPosePredictor(
            model_name=config.model_name, device=config.device, imgsz=config.imgsz
        )
        load_ms = (time.perf_counter() - start) * 1000.0
        label = f"ultralytics-{config.model_format}" if kind != "fake" else "ultralytics"
        return predictor, label, load_ms
    raise ValueError(
        f"Unknown predictor {kind!r}; expected 'fake', 'ultralytics', 'onnx', or 'tensorrt'"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Inference pipeline benchmark (P9).")
    parser.add_argument(
        "--predictor",
        default="fake",
        choices=("fake", "ultralytics", "pytorch", "onnx", "tensorrt"),
    )
    parser.add_argument("--model", default=None, help="Model checkpoint/file name.")
    parser.add_argument(
        "--format",
        default=None,
        choices=("pytorch", "onnx", "tensorrt"),
        help="Model format.",
    )
    parser.add_argument(
        "--precision",
        default=None,
        choices=("fp32", "fp16", "int8"),
        help="Inference precision.",
    )
    parser.add_argument("--warmup", type=int, default=40)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--camera-id", default="bench-cam-01")
    parser.add_argument("--out", default="benchmarks/results/p9_001_baseline.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the inference benchmark; return process exit code."""
    args = parse_args(argv)
    # Infer format, model, and precision if not explicitly set
    if args.predictor == "onnx" or (args.format == "onnx"):
        fmt = "onnx"
        model = args.model or "yolo26s-pose.onnx"
        prec = args.precision or "fp32"
    elif args.predictor == "tensorrt" or (args.format == "tensorrt"):
        fmt = "tensorrt"
        model = args.model or "yolo26s-pose.engine"
        prec = args.precision or "fp16"
    else:
        fmt = args.format or "pytorch"
        model = args.model or "yolo26s-pose.pt"
        prec = args.precision or "fp32"

    config = BenchmarkConfig(
        model_name=model,
        model_format=fmt,
        precision=prec,
        warmup_frames=args.warmup,
        measured_frames=args.frames,
        repetitions=args.reps,
        seed=args.seed,
        frame_height=args.height,
        frame_width=args.width,
        camera_id=args.camera_id,
    )
    predictor, predictor_name, load_ms = build_predictor(args.predictor, config)
    frames = generate_frames(config)
    environment = collect_environment()
    rss_baseline = read_rss_mb()
    reset_vram_peak()
    runs = [run_once(config, predictor, frames) for _ in range(config.repetitions)]
    input_description = {
        "source": "deterministic-synthetic-numpy",
        "resolution": f"{config.frame_width}x{config.frame_height}",
        "frame_count": len(frames),
        "fps": None,
        "input_type": "uint8 HxWx3 seeded RNG",
        "seed": config.seed,
    }
    report = report_to_dict(
        config=config,
        runs=runs,
        environment=environment,
        input_description=input_description,
        predictor_name=predictor_name,
        vram_peak_mb=read_vram_peak_mb(),
        rss_baseline_mb=rss_baseline,
        rss_peak_mb=read_rss_mb(),
        model_load_ms=load_ms,
    )
    target = write_artifact(args.out, report)
    aggregate = report["aggregate"]
    latency = report["latency_all_runs_ms"]
    print(f"predictor : {predictor_name}")
    print(
        f"device    : {environment['device_name'] or 'cpu'} "
        f"(cuda_available={environment['cuda_available']})"
    )
    print(
        f"frames    : {config.measured_frames} measured + {config.warmup_frames} warmup, "
        f"{config.repetitions} reps"
    )
    print(f"fps       : {aggregate['median_fps']:.2f} (median of runs)")
    print(f"mean      : {latency['mean_ms']:.3f} ms")
    print(f"median    : {latency['median_ms']:.3f} ms")
    print(
        f"p90/p95/p99: {latency['p90_ms']:.3f} / {latency['p95_ms']:.3f} / "
        f"{latency['p99_ms']:.3f} ms"
    )
    print(f"artifact  : {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
