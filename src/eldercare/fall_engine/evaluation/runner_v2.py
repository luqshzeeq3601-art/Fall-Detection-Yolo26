"""Sequence evaluation runner for Fall Engine v2 (Phase 11.5)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig, IncidentCooldownManager
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.evaluation.metrics import EvaluationMetrics, compute_metrics
from eldercare.fall_engine.evaluation.runner import SequenceEvalResult
from eldercare.fall_engine.learned_classifier.classifier import LearnedTemporalFallClassifier
from eldercare.fall_engine.state_machine_v2.config_v2 import FallStateMachineConfigV2
from eldercare.fall_engine.state_machine_v2.machine_v2 import TrackFallStateMachineV2
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


class SequenceEvaluationRunnerV2:
    """Executes sequence evaluation over TrackObservation streams using Fall Engine v2."""

    def __init__(
        self,
        config: FallStateMachineConfigV2 | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_config: CooldownConfig | None = None,
        classifier: LearnedTemporalFallClassifier | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfigV2()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_config = cooldown_config or CooldownConfig()
        self.classifier = classifier or LearnedTemporalFallClassifier()

    def evaluate_sequence(
        self,
        observations: Sequence[TrackObservation],
        ground_truth_is_fall: bool,
        ground_truth_onset_sec: float | None = None,
        sample_id: str = "unknown",
        sequence_id: str = "unknown",
        record: SequenceManifestRecord | None = None,
    ) -> SequenceEvalResult:
        """Evaluate a single sequence with Fall Engine v2."""
        cooldown_mgr = IncidentCooldownManager(config=self.cooldown_config)
        sm = TrackFallStateMachineV2(
            camera_id="eval_cam",
            track_id=1,
            config=self.config,
            confidence_config=self.confidence_config,
            cooldown_manager=cooldown_mgr,
            classifier=self.classifier,
        )

        history: list[TrackObservation] = []
        confirmed_event = None
        time_to_alert = None

        for obs in observations:
            history.append(obs)
            _, event = sm.update(history)
            if event is not None and confirmed_event is None:
                confirmed_event = event
                if ground_truth_onset_sec is not None:
                    time_to_alert = max(0.0, event.confirmed_timestamp - ground_truth_onset_sec)

        is_fall_predicted = confirmed_event is not None
        pred_confidence = confirmed_event.confidence if confirmed_event else 0.0

        return SequenceEvalResult(
            sample_id=sample_id,
            sequence_id=sequence_id,
            is_fall_ground_truth=ground_truth_is_fall,
            is_fall_predicted=is_fall_predicted,
            predicted_confidence=pred_confidence,
            time_to_alert_sec=time_to_alert,
            event=confirmed_event,
            final_state=sm.state,
            record=record,
        )

    def evaluate_batch(
        self,
        items: Sequence[tuple[SequenceManifestRecord, Sequence[TrackObservation], float | None]],
    ) -> tuple[EvaluationMetrics, list[SequenceEvalResult]]:
        """Evaluate a batch of sequence tuples."""
        results: list[SequenceEvalResult] = []
        for record, obs_seq, onset_sec in items:
            res = self.evaluate_sequence(
                observations=obs_seq,
                ground_truth_is_fall=record.is_fall,
                ground_truth_onset_sec=onset_sec,
                sample_id=record.sample_id,
                sequence_id=record.sequence_id,
                record=record,
            )
            results.append(res)

        predictions = [r.is_fall_predicted for r in results]
        ground_truths = [r.is_fall_ground_truth for r in results]
        ttas = [r.time_to_alert_sec for r in results if r.time_to_alert_sec is not None]

        metrics = compute_metrics(predictions, ground_truths, ttas)
        return metrics, results
