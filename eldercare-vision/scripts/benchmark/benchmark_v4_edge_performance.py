"""V4 Pipeline Edge & Performance Benchmark on RTX 3070 (P11.7-015).

Measures end-to-end throughput (FPS), stage-by-stage latency breakdowns,
multi-person tracking scalability (1, 2, 4, 8 tracks), and peak memory (RSS + VRAM)
on NVIDIA GeForce RTX 3070.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eldercare.fall_engine.features.multiscale import (
    MultiScaleTemporalFeatures,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.classifier_v4 import GRUClassifierV4
from eldercare.fall_engine.normalization.camera_normalizer import (
    CameraNormalizationConfig,
    CameraPerspectiveNormalizer,
)
from eldercare.fall_engine.pipeline_v4 import FallEnginePipelineV4
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.suppression.adl_suppressor import (
    ADLFalseAlertSuppressor,
    ADLSuppressionConfig,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.pose.inference import UltralyticsPosePredictor
from eldercare.vision.pose.pipeline import PosePipeline, SourceFrame
from eldercare.vision.tracking.history import TrackHistoryConfig
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger("benchmark_v4")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def read_rss_mb() -> float:
    """Read current process Resident Set Size in MB."""
    try:
        import psutil

        return float(psutil.Process(os.getpid()).memory_info().rss) / (1024.0 * 1024.0)
    except Exception:
        return 0.0


def read_vram_peak_mb() -> float:
    """Read peak CUDA VRAM allocated in MB."""
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.max_memory_allocated(0)) / (1024.0 * 1024.0)
    except Exception:
        pass
    return 0.0


def reset_vram_peak() -> None:
    """Reset peak CUDA memory statistics."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats(0)
    except Exception:
        pass


def collect_system_env() -> dict[str, Any]:
    """Collect hardware and software runtime environment."""
    env: dict[str, Any] = {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "cuda_available": False,
        "device_name": "CPU",
        "torch_version": None,
        "ultralytics_version": None,
    }
    try:
        import torch

        env["cuda_available"] = torch.cuda.is_available()
        env["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            env["device_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass

    try:
        import ultralytics

        env["ultralytics_version"] = ultralytics.__version__
    except ImportError:
        pass

    return env


def generate_synthetic_observation(
    camera_id: str,
    track_id: int,
    timestamp: float,
    cx: float = 320.0,
    cy: float = 240.0,
    w: float = 120.0,
    h: float = 260.0,
) -> TrackObservation:
    """Generate realistic TrackObservation with standard 17 COCO keypoints."""
    # Synthetic standing person layout
    ys = [
        cy - h * 0.45,  # nose
        cy - h * 0.47,  # left eye
        cy - h * 0.47,  # right eye
        cy - h * 0.45,  # left ear
        cy - h * 0.45,  # right ear
        cy - h * 0.30,  # left shoulder
        cy - h * 0.30,  # right shoulder
        cy - h * 0.15,  # left elbow
        cy - h * 0.15,  # right elbow
        cy,  # left wrist
        cy,  # right wrist
        cy,  # left hip
        cy,  # right hip
        cy + h * 0.25,  # left knee
        cy + h * 0.25,  # right knee
        cy + h * 0.45,  # left ankle
        cy + h * 0.45,  # right ankle
    ]
    xs = [
        cx,
        cx - 10,
        cx + 10,
        cx - 20,
        cx + 20,
        cx - 30,
        cx + 30,
        cx - 40,
        cx + 40,
        cx - 45,
        cx + 45,
        cx - 25,
        cx + 25,
        cx - 25,
        cx + 25,
        cx - 25,
        cx + 25,
    ]
    kpts_list = []
    for i in range(17):
        kpts_list.append(
            Keypoint(
                present=True,
                x=float(xs[i]),
                y=float(ys[i]),
                confidence=0.92,
            )
        )

    return TrackObservation(
        camera_id=camera_id,
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0),
        detection_confidence=0.95,
        keypoints=tuple(kpts_list),
        image_width=640,
        image_height=480,
    )


def benchmark_v4_pipeline(
    frames_count: int = 500,
    warmup_count: int = 50,
    track_counts: tuple[int, ...] = (1, 2, 4, 8),
) -> dict[str, Any]:
    """Execute rigorous benchmark of FallEnginePipelineV4."""
    env = collect_system_env()
    logger.info("Environment: %s on %s", env["python_version"], env["device_name"])

    # Load frozen V4 components
    model_path = Path("models/temporal_fall_classifier_v4.json")
    if not model_path.is_file():
        model_path = Path("eldercare-vision/models/temporal_fall_classifier_v4.json")

    classifier = GRUClassifierV4.load(model_path) if model_path.is_file() else None
    pipeline = FallEnginePipelineV4(
        config=FallStateMachineConfigV3(
            use_learned_classifier=True,
            classifier_trigger_threshold=0.68,
            classifier_confirmation_threshold=0.69,
            enable_adl_suppression=True,
        ),
        camera_config=CameraNormalizationConfig(
            camera_pitch_deg=25.0,
            camera_height_meters=2.4,
            enabled=True,
        ),
        suppression_config=ADLSuppressionConfig(
            classifier_veto_threshold=0.55,
            enabled=True,
        ),
        classifier=classifier,
    )

    results: dict[str, Any] = {
        "benchmark_version": "1.0.0",
        "phase": "11.7",
        "task": "P11.7-015",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "environment": env,
        "pipeline_config": {
            "camera_pitch_deg": 25.0,
            "camera_height_meters": 2.4,
            "threshold_trigger": 0.68,
            "threshold_confirm": 0.69,
            "threshold_veto": 0.55,
            "history_window_sec": 3.0,
        },
        "scalability_results": {},
        "stage_breakdown_single_track": {},
    }

    # 1. Measure detailed stage breakdown on 1-track scenario
    logger.info("Benchmarking single-track stage breakdown (%d frames)...", frames_count)
    stage_times: dict[str, list[float]] = {
        "perspective_norm_ms": [],
        "multiscale_features_ms": [],
        "gru_inference_ms": [],
        "adl_suppression_ms": [],
        "state_machine_ms": [],
        "total_pipeline_ms": [],
    }

    normalizer = CameraPerspectiveNormalizer(pipeline.camera_config)
    suppressor = ADLFalseAlertSuppressor(pipeline.suppression_config)

    # Warmup
    for i in range(warmup_count):
        t = i * (1.0 / 30.0)
        obs = generate_synthetic_observation("cam-01", 1, t)
        pipeline.process_observation(obs)

    pipeline.reset_all()

    # Measured run
    history_buf: list[TrackObservation] = []
    for i in range(frames_count):
        t = i * (1.0 / 30.0)
        obs = generate_synthetic_observation("cam-01", 1, t)
        history_buf.append(obs)
        if len(history_buf) > 90:
            history_buf.pop(0)

        # Stage 1: Camera perspective normalization
        t0 = time.perf_counter()
        rect_kpts = normalizer.rectify_keypoints(obs.keypoints, 640.0, 480.0)
        t1 = time.perf_counter()

        # Stage 2: Multi-scale feature extraction
        ms_feats = extract_multiscale_temporal_features(history_buf)
        t2 = time.perf_counter()

        # Stage 3: GRU Classifier inference
        prob = 0.0
        if classifier is not None and ms_feats is not None:
            # 24-dim feature vector
            feats_vec = np.array(ms_feats.fused_feature_vector, dtype=np.float32)
            prob = float(classifier.predict_probability(feats_vec))
        t3 = time.perf_counter()

        # Stage 4: ADL suppression check
        supp_res = suppressor.evaluate_suppression(
            features=ms_feats,
            history=history_buf,
            classifier_probability=prob,
        )
        t4 = time.perf_counter()

        # Stage 5: State machine update
        st, ev = pipeline.process_observation(obs)
        t5 = time.perf_counter()

        stage_times["perspective_norm_ms"].append((t1 - t0) * 1000.0)
        stage_times["multiscale_features_ms"].append((t2 - t1) * 1000.0)
        stage_times["gru_inference_ms"].append((t3 - t2) * 1000.0)
        stage_times["adl_suppression_ms"].append((t4 - t3) * 1000.0)
        stage_times["state_machine_ms"].append((t5 - t4) * 1000.0)
        stage_times["total_pipeline_ms"].append((t5 - t0) * 1000.0)

    for stage, times in stage_times.items():
        arr = np.array(times)
        results["stage_breakdown_single_track"][stage] = {
            "mean_ms": float(np.mean(arr)),
            "std_ms": float(np.std(arr)),
            "median_ms": float(np.median(arr)),
            "p95_ms": float(np.percentile(arr, 95)),
            "p99_ms": float(np.percentile(arr, 99)),
            "min_ms": float(np.min(arr)),
            "max_ms": float(np.max(arr)),
        }

    # 2. Multi-track scalability benchmark
    logger.info("Benchmarking multi-track scalability across tracks: %s...", track_counts)
    for num_tracks in track_counts:
        pipeline.reset_all()
        reset_vram_peak()
        rss_start = read_rss_mb()

        # Warmup
        for i in range(warmup_count):
            t = i * (1.0 / 30.0)
            frame_obs = [
                generate_synthetic_observation(
                    "cam-01",
                    tid + 1,
                    t,
                    cx=100.0 + tid * 60.0,
                )
                for tid in range(num_tracks)
            ]
            pipeline.process_frame_observations(frame_obs)

        # Timed loop
        frame_latencies_ms: list[float] = []
        t_start_total = time.perf_counter()

        for i in range(frames_count):
            t = (warmup_count + i) * (1.0 / 30.0)
            frame_obs = [
                generate_synthetic_observation(
                    "cam-01",
                    tid + 1,
                    t,
                    cx=100.0 + tid * 60.0,
                )
                for tid in range(num_tracks)
            ]
            t_f0 = time.perf_counter()
            pipeline.process_frame_observations(frame_obs)
            t_f1 = time.perf_counter()
            frame_latencies_ms.append((t_f1 - t_f0) * 1000.0)

        t_end_total = time.perf_counter()
        total_time_s = t_end_total - t_start_total
        fps = float(frames_count) / total_time_s

        arr_lat = np.array(frame_latencies_ms)
        peak_vram = read_vram_peak_mb()
        peak_rss = read_rss_mb()

        results["scalability_results"][f"{num_tracks}_tracks"] = {
            "tracks_count": num_tracks,
            "fps": fps,
            "latency_ms": {
                "mean_ms": float(np.mean(arr_lat)),
                "std_ms": float(np.std(arr_lat)),
                "median_ms": float(np.median(arr_lat)),
                "p95_ms": float(np.percentile(arr_lat, 95)),
                "p99_ms": float(np.percentile(arr_lat, 99)),
                "min_ms": float(np.min(arr_lat)),
                "max_ms": float(np.max(arr_lat)),
            },
            "memory_mb": {
                "peak_rss_mb": peak_rss,
                "peak_vram_mb": peak_vram,
            },
        }

    # 3. Full End-to-End Estimation with YOLO26s-Pose TensorRT / CUDA
    # From P9-004 TensorRT FP16 baseline on RTX 3070:
    # Pose inference = 4.06 ms (p95 = 4.35 ms)
    # Tracking = 0.52 ms
    # V4 Fall Engine = Mean Latency measured above
    single_track_v4_ms = results["stage_breakdown_single_track"]["total_pipeline_ms"]["mean_ms"]
    trt_pose_ms = 4.0624
    bytetrack_ms = 0.5210
    total_e2e_ms = trt_pose_ms + bytetrack_ms + single_track_v4_ms
    total_e2e_fps = 1000.0 / total_e2e_ms

    results["full_e2e_projection"] = {
        "trt_pose_inference_ms": trt_pose_ms,
        "bytetrack_tracking_ms": bytetrack_ms,
        "v4_fall_engine_ms": single_track_v4_ms,
        "total_e2e_latency_ms": total_e2e_ms,
        "total_e2e_throughput_fps": total_e2e_fps,
        "realtime_target_fps": 30.0,
        "headroom_multiplier": total_e2e_fps / 30.0,
    }

    return results


def main() -> int:
    """Run V4 edge performance benchmark."""
    parser = argparse.ArgumentParser(description="V4 Fall Engine RTX 3070 Benchmark")
    parser.add_argument("--frames", type=int, default=500, help="Number of test frames")
    parser.add_argument("--warmup", type=int, default=50, help="Warmup frame count")
    parser.add_argument(
        "--out",
        default="benchmarks/results/p11_7_015_rtx3070_benchmark.json",
        help="Output JSON file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = benchmark_v4_pipeline(frames_count=args.frames, warmup_count=args.warmup)

    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("Saved benchmark results to %s", out_path)

    # Print summary tables
    print("\n" + "=" * 80)
    print("ELDERCARE VISION V4 — RTX 3070 EDGE & PERFORMANCE BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"Device: {results['environment']['device_name']} | Platform: {results['environment']['platform']}")
    print("-" * 80)
    print(f"{'Pipeline Stage':<35} | {'Mean (ms)':<10} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'p99 (ms)':<10}")
    print("-" * 80)
    for stage, stats in results["stage_breakdown_single_track"].items():
        print(
            f"{stage:<35} | {stats['mean_ms']:<10.4f} | {stats['median_ms']:<10.4f} | {stats['p95_ms']:<10.4f} | {stats['p99_ms']:<10.4f}"
        )
    print("-" * 80)
    print("\nMULTI-TRACK SCALABILITY:")
    print("-" * 80)
    print(f"{'Tracks':<10} | {'FPS':<12} | {'Mean Latency':<15} | {'p95 Latency':<15} | {'Peak VRAM':<12}")
    print("-" * 80)
    for k, v in results["scalability_results"].items():
        lat = v["latency_ms"]
        print(
            f"{v['tracks_count']:<10} | {v['fps']:<12.2f} | {lat['mean_ms']:<15.4f} | {lat['p95_ms']:<15.4f} | {v['memory_mb']['peak_vram_mb']:<12.2f} MB"
        )
    print("-" * 80)
    print("\nFULL END-TO-END PROJECTED SYSTEM (Pose TensorRT FP16 + ByteTrack + V4 Fall Engine):")
    e2e = results["full_e2e_projection"]
    print(f" - YOLO26s-Pose TensorRT FP16 : {e2e['trt_pose_inference_ms']:.3f} ms")
    print(f" - ByteTrack Multi-Tracker     : {e2e['bytetrack_tracking_ms']:.3f} ms")
    print(f" - V4 Fall Detection Engine   : {e2e['v4_fall_engine_ms']:.3f} ms")
    print(f" - Total End-to-End Latency   : {e2e['total_e2e_latency_ms']:.3f} ms")
    print(f" - Total Sustained Throughput : {e2e['total_e2e_throughput_fps']:.2f} FPS")
    print(f" - Real-time Headroom (30 FPS): {e2e['headroom_multiplier']:.2f}x Real-time\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
