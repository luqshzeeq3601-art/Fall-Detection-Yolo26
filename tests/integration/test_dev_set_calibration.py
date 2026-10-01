"""Integration test for development set threshold calibration (P4-007)."""

from __future__ import annotations

from pathlib import Path

from eldercare.fall_engine.calibration import (
    DevelopmentSetCalibrationEvaluator,
    load_fall_detection_config,
)
from eldercare.fall_engine.evaluation import SequenceManifestRecord
from tests.fixtures.synthetic_fall_fixtures import (
    generate_bending_sequence,
    generate_fall_sequence,
    generate_sitting_sequence,
    generate_slow_liedown_sequence,
    generate_walking_sequence,
)


def test_development_set_threshold_calibration_run() -> None:
    """Run full development set calibration using config/fall_detection.yaml.

    Verifies calibrated performance meets acceptance criteria on dev split:
    - Precision >= 0.90
    - Recall >= 0.90
    - F1 >= 0.90
    - 0 False Positives on all standard ADLs (walking, sitting, bending, slow lie down)
    """
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "fall_detection.yaml"
    state_cfg, conf_cfg, cd_cfg = load_fall_detection_config(config_path)

    evaluator = DevelopmentSetCalibrationEvaluator(
        state_config=state_cfg,
        confidence_config=conf_cfg,
        cooldown_config=cd_cfg,
        min_precision_target=0.85,
        min_recall_target=0.90,
    )

    # 1. Build a diverse batch of development sequences
    dev_batch = [
        # Falls (different onset times, durations, directions)
        (
            SequenceManifestRecord(
                sample_id="dev-fall-01",
                source_dataset="URFD",
                sequence_id="fall-01",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="fall_slip",
                is_fall=True,
                fall_type="slip",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="rapid slip",
            ),
            generate_fall_sequence(
                duration_sec=3.5, fps=15.0, fall_start_sec=0.5, direction="right"
            ),
            0.5,
        ),
        (
            SequenceManifestRecord(
                sample_id="dev-fall-02",
                source_dataset="URFD",
                sequence_id="fall-02",
                subject_id="subj-2",
                camera_id="cam-01",
                activity="fall_trip",
                is_fall=True,
                fall_type="trip",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="rapid trip",
            ),
            generate_fall_sequence(
                duration_sec=3.5, fps=15.0, fall_start_sec=0.8, direction="left"
            ),
            0.8,
        ),
        (
            SequenceManifestRecord(
                sample_id="dev-fall-03",
                source_dataset="UP-Fall",
                sequence_id="fall-03",
                subject_id="subj-3",
                camera_id="cam-02",
                activity="fall_backward",
                is_fall=True,
                fall_type="backward",
                path_local="",
                split="dev",
                license="CC-BY-4.0",
                notes="backward fall from standing",
            ),
            generate_fall_sequence(
                duration_sec=4.0, fps=15.0, fall_start_sec=1.0, direction="right"
            ),
            1.0,
        ),
        # ADLs (walking, sitting, bending, slow lie down)
        (
            SequenceManifestRecord(
                sample_id="dev-adl-01",
                source_dataset="URFD",
                sequence_id="adl-01",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="walking",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="standard walking",
            ),
            generate_walking_sequence(duration_sec=3.0, fps=15.0),
            None,
        ),
        (
            SequenceManifestRecord(
                sample_id="dev-adl-02",
                source_dataset="URFD",
                sequence_id="adl-02",
                subject_id="subj-2",
                camera_id="cam-01",
                activity="sitting",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="sitting on chair",
            ),
            generate_sitting_sequence(duration_sec=3.5, fps=15.0),
            None,
        ),
        (
            SequenceManifestRecord(
                sample_id="dev-adl-03",
                source_dataset="UP-Fall",
                sequence_id="adl-03",
                subject_id="subj-3",
                camera_id="cam-02",
                activity="bending",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-4.0",
                notes="picking up object from floor",
            ),
            generate_bending_sequence(duration_sec=3.5, fps=15.0),
            None,
        ),
        (
            SequenceManifestRecord(
                sample_id="dev-adl-04",
                source_dataset="UP-Fall",
                sequence_id="adl-04",
                subject_id="subj-4",
                camera_id="cam-02",
                activity="slow_liedown",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-4.0",
                notes="intentional slow lying down",
            ),
            generate_slow_liedown_sequence(duration_sec=4.0, fps=15.0),
            None,
        ),
    ]

    # 2. Run calibration evaluation
    report, results = evaluator.evaluate_dev_sequences(dev_batch)

    # 3. Assert calibration targets
    assert report.meets_targets is True
    assert report.metrics.total_sequences == 7
    assert report.metrics.tp == 3
    assert report.metrics.tn == 4
    assert report.metrics.fp == 0
    assert report.metrics.fn == 0
    assert report.metrics.precision == 1.0
    assert report.metrics.recall == 1.0
    assert report.metrics.f1 == 1.0
    assert report.adl_rejection_rate == 1.0
    assert report.fall_detection_rate == 1.0

    # Verify time-to-alert
    assert report.metrics.mean_time_to_alert_sec is not None
    assert 0.8 <= report.metrics.mean_time_to_alert_sec <= 2.0
