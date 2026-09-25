"""P11.7-002: Unit tests for metric integrity guardrails and V4 deployment metrics.

Validates:
1. Separation of short-clip ADL false positive rate from long-form false alerts / camera-hour.
2. Accurate Poisson confidence intervals.
3. Provenance verification and quarantine anti-tamper enforcement.
4. Detection of hardcoded evaluation gate literals.
5. Detection of label-leakage in observation generators.
6. Dynamic deployment gate evaluation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eldercare.fall_engine.evaluation.guardrails import (
    HardcodedGateValueDetector,
    LabelLeakageDetector,
    MetricIntegrityGuard,
    sha256_lf,
)
from eldercare.fall_engine.evaluation.metrics_v4 import (
    V4EvaluationResult,
    check_deployment_gates_v4,
    compute_deployment_metrics_v4,
    compute_poisson_confidence_interval,
)

ROOT = Path(__file__).resolve().parents[2]


def test_short_clip_vs_long_form_separation() -> None:
    """Ensure short-clip ADL false positives and continuous long-form stream alerts never mix."""
    # 4 short ADL clips (7s each, 1 FP)
    # 2 long-form streams (1 hour each = 3600 frames at 30 fps, 1 alert on stream 2)
    results = [
        V4EvaluationResult(
            stream_id="adl_clip_1",
            is_fall=False,
            is_short_clip=True,
            is_long_form=False,
            is_true_negative=True,
            actual_decoded_frames=210,
            fps=30.0,
        ),
        V4EvaluationResult(
            stream_id="adl_clip_2",
            is_fall=False,
            is_short_clip=True,
            is_long_form=False,
            is_true_negative=True,
            actual_decoded_frames=210,
            fps=30.0,
        ),
        V4EvaluationResult(
            stream_id="adl_clip_3",
            is_fall=False,
            is_short_clip=True,
            is_long_form=False,
            is_true_negative=True,
            actual_decoded_frames=210,
            fps=30.0,
        ),
        V4EvaluationResult(
            stream_id="adl_clip_4",
            is_fall=False,
            is_short_clip=True,
            is_long_form=False,
            is_false_positive=True,  # 1 short clip FP
            actual_decoded_frames=210,
            fps=30.0,
        ),
        # Long-form stream 1: 0 alerts
        V4EvaluationResult(
            stream_id="stream_cctv_1",
            is_fall=False,
            is_short_clip=False,
            is_long_form=True,
            is_true_negative=True,
            actual_decoded_frames=108000,  # 3600 seconds = 1.0 hour
            fps=30.0,
        ),
        # Long-form stream 2: 1 alert
        V4EvaluationResult(
            stream_id="stream_cctv_2",
            is_fall=False,
            is_short_clip=False,
            is_long_form=True,
            is_false_positive=True,
            actual_decoded_frames=108000,  # 3600 seconds = 1.0 hour
            fps=30.0,
        ),
    ]

    metrics = compute_deployment_metrics_v4(results)

    # 1. Short clip ADL check: 1 FP out of 4 ADL clips = 0.25 (25%)
    assert metrics.short_clip_adl_total_count == 4
    assert metrics.short_clip_adl_fp_count == 1
    assert metrics.short_clip_adl_fp_rate == 0.25

    # 2. Long form stream check: 1 alert across 2.0 actual hours = 0.50 alerts/camera-hour
    assert metrics.long_form_false_alert_count == 1
    assert metrics.long_form_processed_camera_hours == 2.0
    assert metrics.long_form_false_alerts_per_camera_hour == 0.50

    # Short clip duration (840 frames = 28s) was NOT mixed into long-form hours!
    assert metrics.long_form_processed_camera_hours == pytest.approx(2.0, abs=1e-3)


def test_long_form_hours_derived_strictly_from_decoded_frames() -> None:
    """Verify that declared duration cannot be substituted for actual decoded frames."""
    result = V4EvaluationResult(
        stream_id="cctv_partial",
        is_fall=False,
        is_short_clip=False,
        is_long_form=True,
        is_false_positive=False,
        is_true_negative=True,
        declared_duration_seconds=36000.0,  # Declared 10 hours
        actual_decoded_frames=1800,  # 1800 frames at 30 fps = 60s = 0.0167 hours
        fps=30.0,
    )
    metrics = compute_deployment_metrics_v4([result])

    # Must equal actual decoded hours (60 / 3600 = 0.0167), NOT 10.0 hours
    assert metrics.long_form_processed_camera_hours == pytest.approx(60.0 / 3600.0, abs=1e-4)


def test_poisson_confidence_interval() -> None:
    """Verify Poisson confidence interval calculations for event rates."""
    # Zero events over 100 hours
    low, high = compute_poisson_confidence_interval(k=0, exposure_hours=100.0)
    assert low == 0.0
    # Expected upper bound for 0 events: ~3.689 / 100 = 0.0369
    assert high == pytest.approx(0.0369, abs=0.002)

    # 5 events over 100 hours (point estimate = 0.05 / hr)
    low, high = compute_poisson_confidence_interval(k=5, exposure_hours=100.0)
    assert low > 0.0
    assert low < 0.05
    assert high > 0.05
    assert low == pytest.approx(0.0162, abs=0.005)
    assert high == pytest.approx(0.1167, abs=0.005)

    # Zero exposure hours edge case
    assert compute_poisson_confidence_interval(k=0, exposure_hours=0.0) == (0.0, 0.0)


def test_provenance_guard_quarantine_enforcement() -> None:
    """Verify that quarantined artifacts cannot be marked as deployment evidence."""
    guard = MetricIntegrityGuard()

    # Attempting to validate a quarantined file with deployment_evidence=True
    quarantined_rel_path = "experiments/v3/holdout/P11.6_006_deployment_holdout_evaluation.json"
    fake_data = {
        "deployment_evidence": True,
        "provenance": "real_measured",
        "source_file_hashes": {"README.md": sha256_lf(ROOT / "README.md")},
        "actual_processed_seconds": 100.0,
        "actual_decoded_frames": 3000,
    }

    violations = guard.validate_metrics_dict(fake_data, artifact_rel_path=quarantined_rel_path)
    assert any("quarantined in P11.7-001" in v for v in violations)


def test_provenance_guard_synthetic_rejection() -> None:
    """Verify that synthetic simulation provenance is rejected for deployment evidence."""
    guard = MetricIntegrityGuard()
    fake_data = {
        "deployment_evidence": True,
        "provenance": "synthetic_simulation",
        "source_file_hashes": {"README.md": sha256_lf(ROOT / "README.md")},
        "actual_processed_seconds": 100.0,
        "actual_decoded_frames": 3000,
    }
    violations = guard.validate_metrics_dict(fake_data)
    assert any("requires provenance='real_measured'" in v for v in violations)


def test_provenance_guard_hash_validation() -> None:
    """Verify that missing or tampered source files trigger validation errors."""
    guard = MetricIntegrityGuard()

    # Tampered hash
    fake_data = {
        "deployment_evidence": True,
        "provenance": "real_measured",
        "source_file_hashes": {
            "README.md": "0000000000000000000000000000000000000000000000000000000000000000"
        },
        "actual_processed_seconds": 100.0,
        "actual_decoded_frames": 3000,
    }
    violations = guard.validate_metrics_dict(fake_data)
    assert any("hash mismatch" in v for v in violations)


def test_hardcoded_gate_detector() -> None:
    """Verify that hardcoded gate outcomes in code AST are flagged."""
    detector = HardcodedGateValueDetector()

    suspicious_code = """
def evaluate():
    metrics = {
        "recall": 0.9444,
        "false_alerts_per_camera_hour": 0.02,
        "pose_availability_rate": 0.9663,
    }
    return metrics
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(suspicious_code)
        f_path = Path(f.name)

    try:
        findings = detector.scan_file(f_path)
        assert len(findings) == 3
        flagged_metrics = {f["metric"] for f in findings}
        assert "recall" in flagged_metrics
        assert "false_alerts_per_camera_hour" in flagged_metrics
        assert "pose_availability_rate" in flagged_metrics
    finally:
        f_path.unlink(missing_ok=True)


def test_label_leakage_detector() -> None:
    """Verify that code branching or assigning is_fall in observation generators is flagged."""
    detector = LabelLeakageDetector()

    leaky_code = """
def generate_observations(record):
    is_fall = int(record["is_fall"]) == 1
    if is_fall:
        return [make_fall_box()]
    return [make_walk_box()]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(leaky_code)
        f_path = Path(f.name)

    try:
        findings = detector.scan_file(f_path)
        assert len(findings) >= 1
        assert any(f["target"] == "is_fall" for f in findings)
    finally:
        f_path.unlink(missing_ok=True)


def test_deployment_gate_evaluation_v4() -> None:
    """Verify dynamic deployment gate checking against defined targets."""
    # Create passing metrics
    passing_results = [
        V4EvaluationResult(
            stream_id=f"fall_{i}",
            is_fall=True,
            is_true_positive=True,
            actual_decoded_frames=300,
            fps=30.0,
            time_to_alert_sec=1.5,
            total_frames_in_fall_window=100,
            frames_with_usable_pose=98,
            expected_track_frames=100,
            continuous_track_frames=99,
        )
        for i in range(20)
    ]
    # Add 1 long-form stream (100 hours = 360,000s, 0 false alerts)
    passing_results.append(
        V4EvaluationResult(
            stream_id="long_cctv",
            is_fall=False,
            is_short_clip=False,
            is_long_form=True,
            is_true_negative=True,
            actual_decoded_frames=10800000,
            fps=30.0,
        )
    )

    metrics = compute_deployment_metrics_v4(passing_results, throughput_fps=45.0)

    targets = {
        "recall": 0.95,
        "precision": 0.95,
        "long_form_false_alerts_per_camera_hour": 0.02,
        "p95_tta_sec": 2.5,
        "usable_pose_rate": 0.95,
        "track_continuity_rate": 0.95,
        "throughput_fps": 30.0,
    }

    report = check_deployment_gates_v4(metrics, targets)
    assert report["all_passed"] is True
    assert len(report["not_met"]) == 0
    assert len(report["met"]) == 7

    # Failing target test
    failing_targets = {"recall": 1.05}  # Impossible recall
    fail_report = check_deployment_gates_v4(metrics, failing_targets)
    assert fail_report["all_passed"] is False
    assert len(fail_report["not_met"]) == 1
