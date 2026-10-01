from eldercare.fall_engine.evaluation.metrics_v3 import (
    V3EvaluationResult,
    check_deployment_gates,
    compute_deployment_metrics_v3,
)


def test_f2_score():
    results = [
        V3EvaluationResult(is_true_positive=True),  # TP
        V3EvaluationResult(is_true_positive=True),  # TP
        V3EvaluationResult(is_false_negative=True),  # FN
        V3EvaluationResult(is_false_positive=True),  # FP
    ]
    # TP=2, FN=1, FP=1
    # P = 2/3 = 0.666
    # R = 2/3 = 0.666
    # F2 = (5 * 2/3 * 2/3) / (4 * 2/3 + 2/3) = (20/9) / (10/3) = (20/9) * (3/10) = 60/90 = 0.666
    metrics = compute_deployment_metrics_v3(results)
    assert abs(metrics.f2_score - 0.6666) < 0.01


def test_false_alerts_per_hour():
    results = [
        V3EvaluationResult(is_false_positive=True, non_fall_duration_hours=0.5),
        V3EvaluationResult(is_false_positive=True, non_fall_duration_hours=0.5),
        V3EvaluationResult(is_true_negative=True, non_fall_duration_hours=1.0),
    ]
    metrics = compute_deployment_metrics_v3(results)
    # FP=2, total_hours = 2.0 -> FA/hr = 1.0
    assert metrics.false_alerts_per_camera_hour == 1.0


def test_tta_percentiles():
    results = [
        V3EvaluationResult(is_true_positive=True, time_to_alert_ms=100.0),
        V3EvaluationResult(is_true_positive=True, time_to_alert_ms=200.0),
        V3EvaluationResult(is_true_positive=True, time_to_alert_ms=300.0),
        V3EvaluationResult(is_true_positive=True, time_to_alert_ms=400.0),
        V3EvaluationResult(is_true_positive=True, time_to_alert_ms=500.0),
    ]
    metrics = compute_deployment_metrics_v3(results)
    assert metrics.median_tta == 300.0
    assert metrics.p90_tta == 460.0  # 0.9 * 4 = 3.6 -> idx 3.6 -> 400 + 0.6*(500-400) = 460


def test_gate_checking():
    results = [
        V3EvaluationResult(is_true_positive=True),
        V3EvaluationResult(is_true_positive=True),
    ]
    metrics = compute_deployment_metrics_v3(results)
    targets = {"f2_score": 0.9, "false_alerts_per_camera_hour": 0.1}
    # F2 will be 1.0, FA/hr will be 0.0
    report = check_deployment_gates(metrics, targets)
    assert len(report["met"]) == 2
    assert len(report["not_met"]) == 0


def test_edge_cases():
    # Empty
    metrics = compute_deployment_metrics_v3([])
    assert metrics.f2_score == 0.0

    # Only FN
    metrics = compute_deployment_metrics_v3([V3EvaluationResult(is_false_negative=True)])
    assert metrics.f2_score == 0.0
    assert metrics.missed_fall_rate == 1.0
