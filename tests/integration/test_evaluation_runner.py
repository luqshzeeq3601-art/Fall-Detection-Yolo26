"""Integration tests for the dataset sequence evaluation runner (P4-005)."""

from __future__ import annotations

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.evaluation.metrics import EvaluationMetrics
from eldercare.fall_engine.evaluation.runner import (
    SequenceEvalResult,
    SequenceEvaluationRunner,
)
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from tests.fixtures.synthetic_fall_fixtures import (
    generate_bending_sequence,
    generate_fall_sequence,
    generate_sitting_sequence,
    generate_slow_liedown_sequence,
    generate_walking_sequence,
)


def test_evaluation_runner_batch_on_synthetic_dev_set() -> None:
    """Evaluation runner evaluates a synthetic batch of falls and ADLs.

    Computes clean confusion matrix metrics without leakage.
    """
    runner = SequenceEvaluationRunner(
        config=FallStateMachineConfig(down_confirmation_sec=0.8),
        confidence_config=FallConfidenceConfig(),
    )

    batch_items = [
        # Fall 1: rapid slip
        (
            SequenceManifestRecord(
                sample_id="dev-fall-01",
                source_dataset="URFD",
                sequence_id="fall-01",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="fall",
                is_fall=True,
                fall_type="slip",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="",
            ),
            generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5),
            0.5,
        ),
        # Fall 2: rapid trip
        (
            SequenceManifestRecord(
                sample_id="dev-fall-02",
                source_dataset="URFD",
                sequence_id="fall-02",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="fall",
                is_fall=True,
                fall_type="trip",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="",
            ),
            generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.6),
            0.6,
        ),
        # ADL 1: walking
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
                notes="",
            ),
            generate_walking_sequence(duration_sec=3.0, fps=15.0),
            None,
        ),
        # ADL 2: sitting
        (
            SequenceManifestRecord(
                sample_id="dev-adl-02",
                source_dataset="URFD",
                sequence_id="adl-02",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="sitting",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="",
            ),
            generate_sitting_sequence(duration_sec=3.0, fps=15.0),
            None,
        ),
        # ADL 3: bending
        (
            SequenceManifestRecord(
                sample_id="dev-adl-03",
                source_dataset="URFD",
                sequence_id="adl-03",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="bending",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="",
            ),
            generate_bending_sequence(duration_sec=3.0, fps=15.0),
            None,
        ),
        # ADL 4: slow lie down
        (
            SequenceManifestRecord(
                sample_id="dev-adl-04",
                source_dataset="URFD",
                sequence_id="adl-04",
                subject_id="subj-1",
                camera_id="cam-01",
                activity="lying",
                is_fall=False,
                fall_type="none",
                path_local="",
                split="dev",
                license="CC-BY-NC-SA-4.0",
                notes="",
            ),
            generate_slow_liedown_sequence(duration_sec=4.0, fps=15.0),
            None,
        ),
    ]

    metrics, results = runner.evaluate_batch(batch_items)

    assert isinstance(metrics, EvaluationMetrics)
    assert metrics.total_sequences == 6
    assert metrics.tp == 2
    assert metrics.tn == 4
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.accuracy == 1.0
    assert metrics.mean_time_to_alert_sec is not None
    assert metrics.mean_time_to_alert_sec < 2.0  # Fast time-to-alert under 2 seconds


def test_evaluation_runner_handles_empty_stream() -> None:
    """Empty stream returns negative prediction safely."""
    runner = SequenceEvaluationRunner()
    res = runner.evaluate_sequence(
        sample_id="empty-01",
        sequence_id="empty-seq",
        is_fall_ground_truth=True,
        observations=[],
    )
    assert isinstance(res, SequenceEvalResult)
    assert not res.is_fall_predicted
    assert res.time_to_alert_sec is None
