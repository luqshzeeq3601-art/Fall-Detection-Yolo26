"""Development set calibration evaluator with strict anti-leakage protection (P4-007)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.evaluation.metrics import EvaluationMetrics
from eldercare.fall_engine.evaluation.runner import (
    SequenceEvalResult,
    SequenceEvaluationRunner,
)
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class CalibrationReport:
    """Structured report produced by development set threshold calibration."""

    metrics: EvaluationMetrics
    activity_breakdown: dict[str, dict[str, int]]
    adl_rejection_rate: float
    fall_detection_rate: float
    meets_targets: bool
    config_summary: dict[str, Any] = field(default_factory=dict)


class DevelopmentSetCalibrationEvaluator:
    """Evaluates threshold configurations strictly on development set partitions.

    Guarantees zero test split touch: any attempt to evaluate test-partition
    sequences fails closed immediately with an anti-leakage ValueError.
    """

    def __init__(
        self,
        state_config: FallStateMachineConfig | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_config: CooldownConfig | None = None,
        min_precision_target: float = 0.85,
        min_recall_target: float = 0.90,
    ) -> None:
        self.state_config = state_config or FallStateMachineConfig()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_config = cooldown_config or CooldownConfig()
        self.min_precision_target = min_precision_target
        self.min_recall_target = min_recall_target

    def evaluate_dev_sequences(
        self,
        items: Sequence[tuple[SequenceManifestRecord, Sequence[TrackObservation], float | None]],
    ) -> tuple[CalibrationReport, list[SequenceEvalResult]]:
        """Evaluate a batch of development set sequences.

        Args:
            items: Sequence of (manifest_record, observations, ground_truth_onset_sec).

        Returns:
            Tuple of (CalibrationReport, list[SequenceEvalResult]).

        Raises:
            ValueError: If any item belongs to a non-dev split (e.g. 'test').
        """
        # 1. Anti-leakage verification: every sequence must be strictly 'dev'
        for record, _, _ in items:
            if record.split != "dev":
                raise ValueError(
                    "Data leakage detected: calibration must run ONLY on dev sequences, "
                    f"got sample_id={record.sample_id!r} with split={record.split!r}"
                )

        runner = SequenceEvaluationRunner(
            config=self.state_config,
            confidence_config=self.confidence_config,
            cooldown_config=self.cooldown_config,
        )

        metrics, results = runner.evaluate_batch(items)

        # 2. Compute activity-level breakdown
        activity_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "detected_fall": 0, "correct": 0}
        )
        for res in results:
            act = res.record.activity if res.record else "unknown"
            activity_stats[act]["total"] += 1
            if res.detected_fall:
                activity_stats[act]["detected_fall"] += 1
            if res.correct:
                activity_stats[act]["correct"] += 1

        total_adls = metrics.tn + metrics.fp
        adl_rejection_rate = (metrics.tn / total_adls) if total_adls > 0 else 1.0

        total_falls = metrics.tp + metrics.fn
        fall_detection_rate = (metrics.tp / total_falls) if total_falls > 0 else 1.0

        meets_targets = (
            metrics.precision >= self.min_precision_target
            and metrics.recall >= self.min_recall_target
        )

        report = CalibrationReport(
            metrics=metrics,
            activity_breakdown=dict(activity_stats),
            adl_rejection_rate=adl_rejection_rate,
            fall_detection_rate=fall_detection_rate,
            meets_targets=meets_targets,
            config_summary={
                "descent_velocity_threshold": self.state_config.descent_velocity_threshold,
                "peak_velocity_threshold": self.state_config.peak_descent_velocity_threshold,
                "fallen_aspect_ratio_max": self.state_config.fallen_aspect_ratio_max,
                "fallen_torso_angle_max_deg": self.state_config.fallen_torso_angle_max_deg,
                "down_confirmation_sec": self.state_config.down_confirmation_sec,
                "min_confidence_to_confirm": self.confidence_config.min_confidence_to_confirm,
            },
        )

        return report, results
