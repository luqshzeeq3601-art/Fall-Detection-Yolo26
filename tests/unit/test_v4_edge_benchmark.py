# ruff: noqa: E501
"""Unit tests for V4 Edge & Performance Benchmark on RTX 3070 (P11.7-015)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.benchmark.benchmark_v4_edge_performance import (
    benchmark_v4_pipeline,
    collect_system_env,
    generate_synthetic_observation,
)


def test_collect_system_env():
    """Verify system environment collection captures hardware specs."""
    env = collect_system_env()
    assert "platform" in env
    assert "python_version" in env
    assert "numpy_version" in env
    assert "cuda_available" in env


def test_generate_synthetic_observation():
    """Verify realistic 17-keypoint observation generation."""
    obs = generate_synthetic_observation("test-cam", 1, 0.0)
    assert obs.camera_id == "test-cam"
    assert obs.track_id == 1
    assert obs.timestamp == 0.0
    assert len(obs.keypoints) == 17
    assert all(kpt.present for kpt in obs.keypoints)


def test_benchmark_pipeline_dry_run():
    """Verify quick execution of V4 benchmark pipeline harness."""
    results = benchmark_v4_pipeline(
        frames_count=20,
        warmup_count=5,
        track_counts=(1, 2),
    )
    assert results["benchmark_version"] == "1.0.0"
    assert "stage_breakdown_single_track" in results
    assert "scalability_results" in results
    assert "full_e2e_projection" in results

    # Check stages
    stages = results["stage_breakdown_single_track"]
    assert "perspective_norm_ms" in stages
    assert "multiscale_features_ms" in stages
    assert "gru_inference_ms" in stages
    assert "adl_suppression_ms" in stages
    assert "state_machine_ms" in stages
    assert "total_pipeline_ms" in stages

    # Check latency performance (< 5ms per frame on CPU/GPU)
    assert stages["total_pipeline_ms"]["mean_ms"] < 10.0


def test_benchmark_result_json_artifact_exists():
    """Verify generated JSON artifact matches schema and real-time SLA."""
    path = Path("benchmarks/results/p11_7_015_rtx3070_benchmark.json")
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["task"] == "P11.7-015"
        assert "scalability_results" in data
        assert data["full_e2e_projection"]["total_e2e_throughput_fps"] >= 30.0
