"""Unit tests for Phase 11.8 V5 Freeze Manifest Verification and Final Deployment Gate."""

from eldercare.fall_engine.evaluation.metrics_v4 import (
    DeploymentMetricsV4,
    check_deployment_gates_v4,
    load_phase_gate_targets,
)
from scripts.dataset.evaluate_v5 import verify_freeze_manifest_v5
from tests.local_artifacts import requires_local


def _make_metrics(
    recall: float = 0.96,
    precision: float = 0.95,
    f1_score: float = 0.955,
    far_hr: float = 0.35,
    p95_tta: float = 1.2,
    fps: float = 22.5,
    continuity: float = 0.98,
    extra_tracks: float = 0.02,
) -> DeploymentMetricsV4:
    return DeploymentMetricsV4(
        tp=100,
        fp=5,
        tn=200,
        fn=4,
        total_sequences=309,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        f2_score=0.958,
        accuracy=0.97,
        missed_fall_rate=1.0 - recall,
        short_clip_adl_fp_count=5,
        short_clip_adl_total_count=205,
        short_clip_adl_fp_rate=0.024,
        long_form_false_alert_count=2,
        long_form_processed_camera_hours=10.0,
        long_form_false_alerts_per_camera_hour=far_hr,
        long_form_fa_poisson_ci=(0.1, 0.6),
        actual_processed_seconds=36000.0,
        actual_decoded_frames=540000,
        median_tta_sec=0.8,
        p90_tta_sec=1.1,
        p95_tta_sec=p95_tta,
        tta_samples=100,
        duplicate_alert_rate=0.0,
        usable_pose_rate=0.99,
        track_continuity_rate=continuity,
        id_switch_rate=0.01,
        throughput_fps=fps,
        p50_latency_ms=1.2,
        p95_latency_ms=2.5,
        e2e_alert_latency_sec=1.2,
        hardware_metrics={},
        subgroup_metrics={},
        provenance="test_v5_evidence",
        deployment_evidence=True,
        source_file_hashes={},
        input_manifest_hash="sha256:abcd",
        evaluated_at_utc="2026-09-25T12:00:00Z",
        notes="v5 deployment test",
        extra_tracks_per_frame=extra_tracks,
    )


@requires_local("models/temporal_skeleton_classifier_v5.pt")
def test_v5_freeze_manifest_integrity() -> None:
    """Verify that all frozen V5 artifacts exist and match cryptographic hashes."""
    manifest = verify_freeze_manifest_v5()
    assert manifest["phase"] == "11.8"
    assert len(manifest["artifacts"]) >= 6


def test_v5_deployment_gate_pass_criteria() -> None:
    """Verify that meeting deployment targets passes the deployment gate."""
    targets = load_phase_gate_targets()
    metrics = _make_metrics(
        recall=0.96,
        precision=0.95,
        f1_score=0.955,
        far_hr=0.35,
        p95_tta=1.2,
        fps=22.5,
        continuity=0.98,
        extra_tracks=0.02,
    )

    gate_result = check_deployment_gates_v4(metrics, targets)
    assert gate_result["all_passed"] is True
    assert len(gate_result["not_met"]) == 0
    assert len(gate_result["met"]) >= 5


def test_v5_deployment_gate_fail_criteria() -> None:
    """Verify that failing deployment targets fails the deployment gate."""
    targets = load_phase_gate_targets()
    # Recall and FAR/hr violate deployment gate
    metrics = _make_metrics(
        recall=0.88,
        precision=0.91,
        f1_score=0.895,
        far_hr=2.5,
        p95_tta=3.2,
        fps=11.0,
        continuity=0.75,
        extra_tracks=0.25,
    )

    gate_result = check_deployment_gates_v4(metrics, targets)
    assert gate_result["all_passed"] is False
    assert len(gate_result["not_met"]) >= 3
