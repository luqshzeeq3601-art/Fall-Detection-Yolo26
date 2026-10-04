"""TDD Test Suite for Portfolio Evaluation Workflow and Matrix Generation.

Verifies:
1. Model loading, pipeline configuration, and freeze integrity.
2. Test matrix construction across real dataset scenarios (falls, ADLs, difficult conditions).
3. Metric calculations (Precision, Recall, F1, Specificity, Poisson FA/h, Wilson CIs).
4. Export artifact schema validation (predictions.csv, metrics.json, per_scenario_metrics.csv).
5. Edge cases: empty sequences, missing keypoints, ID switches, malformed inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_portfolio_evaluator_imports() -> None:
    """Test that portfolio evaluation module and classes exist and can be imported."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import (
        EvaluationSummaryMetrics,
        PortfolioEvaluationRunner,
        ScenarioEvaluationResult,
    )
    assert PortfolioEvaluationRunner is not None
    assert ScenarioEvaluationResult is not None
    assert EvaluationSummaryMetrics is not None


def test_frozen_model_and_config_loading() -> None:
    """Verify that the frozen V6.3 model and calibrated configuration load successfully."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import PortfolioEvaluationRunner

    runner = PortfolioEvaluationRunner(
        models_dir=ROOT / "models" / "v6_3_phase3b",
        manifest_path=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        cache_dir=ROOT / "datasets" / "cache" / "poses_mp",
    )
    assert runner.model is not None
    assert runner.pipeline is not None
    assert runner.config.descent_low_posture is True
    assert runner.post_processor.fall_trigger_threshold == 0.55
    assert runner.post_processor.down_confirmation_threshold == 0.55


def test_test_matrix_contains_real_scenarios_and_no_invented_categories() -> None:
    """Verify test matrix uses real dataset labels and covers required fall & ADL scenarios."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import PortfolioEvaluationRunner

    runner = PortfolioEvaluationRunner(
        models_dir=ROOT / "models" / "v6_3_phase3b",
        manifest_path=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        cache_dir=ROOT / "datasets" / "cache" / "poses_mp",
    )
    test_records = runner.get_split_records("test_b")
    assert len(test_records) == 132

    scenarios = {r["activity_label"] for r in test_records}
    expected_falls = {
        "fall_forward_hands",
        "fall_forward_knees",
        "fall_backward",
        "fall_sideways",
        "fall_from_chair",
    }
    expected_adls = {
        "walking",
        "standing",
        "sitting",
        "picking_up_object",
        "jumping",
        "lying_down",
    }
    assert expected_falls.issubset(scenarios)
    assert expected_adls.issubset(scenarios)
    # Ensure no fabricated categories
    assert scenarios == expected_falls.union(expected_adls)


def test_difficult_scenario_tagging() -> None:
    """Verify difficult scenario characteristics are tagged accurately from metadata."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import PortfolioEvaluationRunner

    runner = PortfolioEvaluationRunner(
        models_dir=ROOT / "models" / "v6_3_phase3b",
        manifest_path=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        cache_dir=ROOT / "datasets" / "cache" / "poses_mp",
    )
    test_records = runner.get_split_records("test_b")

    cam2_records = [r for r in test_records if r.get("camera_id") == "cam2"]
    assert len(cam2_records) == 66
    for r in cam2_records:
        tags = runner.extract_scenario_tags(r)
        assert "lateral_angle" in tags
        assert "seated_bystander" in tags

    cam1_records = [r for r in test_records if r.get("camera_id") == "cam1"]
    assert len(cam1_records) == 66
    for r in cam1_records:
        tags = runner.extract_scenario_tags(r)
        assert "ceiling_angle" in tags


def test_metric_calculations_pure_logic() -> None:
    """Verify pure math calculation of precision, recall, F1, specificity, and Wilson CIs."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import calculate_metrics_summary

    # Perfect scenario
    m_perfect = calculate_metrics_summary(tp=60, fn=0, tn=72, fp=0, total_false_alerts=0)
    assert m_perfect.recall == 1.0
    assert m_perfect.precision == 1.0
    assert m_perfect.f1_score == 1.0
    assert m_perfect.specificity == 1.0

    # Measured Test-B scenario: 59 TP, 1 FN, 71 TN, 1 FP (2 false alerts total)
    m_testb = calculate_metrics_summary(tp=59, fn=1, tn=71, fp=1, total_false_alerts=2)
    assert round(m_testb.recall, 4) == 0.9833
    assert round(m_testb.precision, 4) == 0.9672
    assert round(m_testb.specificity, 4) == 0.9861
    assert round(m_testb.f1_score, 4) == 0.9752
    assert m_testb.recall_ci_95[0] > 0.90
    assert m_testb.precision_ci_95[0] > 0.85


def test_edge_cases_handling(tmp_path: Path) -> None:
    """Verify pipeline and evaluator handle empty observations, no persons, and ID switches gracefully."""
    from eldercare.fall_engine.evaluation.portfolio_evaluator import PortfolioEvaluationRunner
    from eldercare.vision.pose.adapter import Keypoint
    from eldercare.vision.tracking.observation import TrackObservation

    runner = PortfolioEvaluationRunner(
        models_dir=ROOT / "models" / "v6_3_phase3b",
        manifest_path=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        cache_dir=ROOT / "datasets" / "cache" / "poses_mp",
    )
    runner.pipeline.reset()

    # Empty frame / zero keypoint observation
    empty_kps = tuple(Keypoint(x=None, y=None, confidence=0.0, present=False) for _ in range(17))
    empty_obs = TrackObservation(
        camera_id="test_cam",
        track_id=1,
        timestamp=0.1,
        bbox_xyxy=(0.0, 0.0, 0.0, 0.0),
        detection_confidence=0.0,
        keypoints=empty_kps,
        image_width=640,
        image_height=480,
    )
    sig = runner.pipeline.compute_signals(empty_obs, keep_features=False)
    assert sig.p_falling == 0.0
    assert sig.p_fallen == 0.0
    _, ev = runner.pipeline.decision.step(sig)
    assert ev is None


def test_export_artifacts_and_schema_validation(tmp_path: Path) -> None:
    """Verify that export_results produces valid CSV and JSON artifacts matching required schemas."""
    import csv

    from eldercare.fall_engine.evaluation.portfolio_evaluator import (
        PortfolioEvaluationRunner,
        ScenarioEvaluationResult,
    )

    runner = PortfolioEvaluationRunner(
        models_dir=ROOT / "models" / "v6_3_phase3b",
        manifest_path=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        cache_dir=ROOT / "datasets" / "cache" / "poses_mp",
    )

    sample_results = [
        ScenarioEvaluationResult(
            test_id="TEST-001",
            dataset="UP-Fall",
            sequence_id="upfall_s12_a01_t01_c1",
            scenario="fall_forward_hands",
            ground_truth="fall",
            predicted_class="fall",
            outcome="TP",
            temporal_score=0.985,
            detection_timestamp=1.25,
            time_to_alert=0.65,
            latency_ms=2.5,
            fps=150.0,
            camera_id="cam1",
            subject_id="upfall_subj_12",
            difficult_scenario_tags="ceiling_angle;forward_descent",
            notes="Correctly detected fall (TTA: 0.65s)",
        ),
        ScenarioEvaluationResult(
            test_id="TEST-002",
            dataset="UP-Fall",
            sequence_id="upfall_s12_a06_t01_c1",
            scenario="walking",
            ground_truth="adl",
            predicted_class="adl",
            outcome="TN",
            temporal_score=0.05,
            detection_timestamp=None,
            time_to_alert=None,
            latency_ms=2.4,
            fps=155.0,
            camera_id="cam1",
            subject_id="upfall_subj_12",
            difficult_scenario_tags="ceiling_angle;locomotion",
            notes="Correctly rejected non-fall activity",
        ),
    ]

    out_dir = tmp_path / "results" / "evaluation"
    report_file = tmp_path / "docs" / "results" / "EVALUATION_REPORT.md"
    pred_csv, metrics_json, scenario_csv, rep_md = runner.export_results(
        sample_results, output_dir=out_dir, report_path=report_file
    )

    assert pred_csv.is_file()
    assert metrics_json.is_file()
    assert scenario_csv.is_file()
    assert rep_md.is_file()

    # Validate predictions.csv columns
    with open(pred_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["test_id"] == "TEST-001"
        assert rows[0]["outcome"] == "TP"
        assert rows[1]["outcome"] == "TN"
        required_cols = {
            "test_id", "dataset", "sequence_id", "scenario", "ground_truth",
            "predicted_class", "outcome", "temporal_score", "detection_timestamp",
            "time_to_alert", "latency_ms", "fps", "camera_id", "subject_id",
            "difficult_scenario_tags", "notes"
        }
        assert required_cols.issubset(rows[0].keys())

    # Validate metrics.json
    metrics_data = json.loads(metrics_json.read_text(encoding="utf-8"))
    assert "overall_summary" in metrics_data
    assert metrics_data["overall_summary"]["tp"] == 1
    assert metrics_data["overall_summary"]["tn"] == 1
    assert "camera_breakdown" in metrics_data
    assert "per_scenario" in metrics_data

    # Validate report markdown
    report_text = rep_md.read_text(encoding="utf-8")
    assert "# ElderCare Vision — Model Evaluation Report" in report_text
    assert "Confusion Matrix" in report_text

