"""Sequence evaluation runner for testing the fall engine against dataset sequences (P4-005)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.evaluation.metrics import EvaluationMetrics, compute_metrics
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from eldercare.fall_engine.state_machine.machine import TrackFallStateMachine
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SequenceEvalResult:
    """Evaluation result for a single sequence."""

    sample_id: str
    sequence_id: str
    is_fall_ground_truth: bool
    is_fall_predicted: bool
    predicted_confidence: float
    time_to_alert_sec: float | None
    event: FallEvent | None
    final_state: FallState
    record: SequenceManifestRecord | None = None

    @property
    def correct(self) -> bool:
        """True if prediction matches ground truth."""
        return self.is_fall_predicted == self.is_fall_ground_truth

    @property
    def detected_fall(self) -> bool:
        """True if fall was predicted."""
        return self.is_fall_predicted


class SequenceEvaluationRunner:
    """Executes deterministic sequence-level evaluation over track observation streams."""

    def __init__(
        self,
        config: FallStateMachineConfig | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_config: CooldownConfig | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfig()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_config = cooldown_config or CooldownConfig()

    def evaluate_sequence(
        self,
        sample_id: str,
        sequence_id: str,
        is_fall_ground_truth: bool,
        observations: Sequence[TrackObservation],
        fall_onset_timestamp: float | None = None,
        record: SequenceManifestRecord | None = None,
    ) -> SequenceEvalResult:
        """Run a single sequence of observations through the fall state machine.

        Args:
            sample_id: Unique sample identifier.
            sequence_id: Video sequence identifier.
            is_fall_ground_truth: True if sequence contains a true fall.
            observations: Chronological sequence of TrackObservation.
            fall_onset_timestamp: Known start time of the fall descent (for time-to-alert).
            record: Optional manifest record for provenance attachment.

        Returns:
            SequenceEvalResult detailing classification and timing.
        """
        if not observations:
            return SequenceEvalResult(
                sample_id=sample_id,
                sequence_id=sequence_id,
                is_fall_ground_truth=is_fall_ground_truth,
                is_fall_predicted=False,
                predicted_confidence=0.0,
                time_to_alert_sec=None,
                event=None,
                final_state=FallState.NORMAL,
                record=record,
            )

        camera_id = observations[0].camera_id or "cam-eval"
        track_id = observations[0].track_id if observations[0].track_id is not None else 1

        sm = TrackFallStateMachine(
            camera_id=camera_id,
            track_id=track_id,
            config=self.config,
            confidence_config=self.confidence_config,
        )

        detected_event: FallEvent | None = None

        for i in range(1, len(observations) + 1):
            history_slice = observations[:i]
            _, event = sm.update(history_slice)
            if event is not None and detected_event is None:
                detected_event = event

        is_predicted = detected_event is not None
        confidence = detected_event.confidence if detected_event is not None else 0.0

        time_to_alert = None
        if detected_event is not None:
            if fall_onset_timestamp is not None:
                time_to_alert = max(0.0, detected_event.confirmed_timestamp - fall_onset_timestamp)
            else:
                time_to_alert = max(
                    0.0,
                    detected_event.confirmed_timestamp - detected_event.candidate_timestamp,
                )

        return SequenceEvalResult(
            sample_id=sample_id,
            sequence_id=sequence_id,
            is_fall_ground_truth=is_fall_ground_truth,
            is_fall_predicted=is_predicted,
            predicted_confidence=confidence,
            time_to_alert_sec=time_to_alert,
            event=detected_event,
            final_state=sm.state,
            record=record,
        )

    def evaluate_batch(
        self,
        items: Sequence[
            tuple[
                SequenceManifestRecord,
                Sequence[TrackObservation],
                float | None,
            ]
        ],
    ) -> tuple[EvaluationMetrics, list[SequenceEvalResult]]:
        """Evaluate a batch of manifest records with their observation streams.

        Args:
            items: List of (manifest_record, observation_stream, optional_fall_onset_sec).

        Returns:
            Tuple of (EvaluationMetrics, list of SequenceEvalResult).
        """
        results: list[SequenceEvalResult] = []
        tp = fp = tn = fn = 0
        alert_times: list[float] = []

        for record, observations, onset_time in items:
            res = self.evaluate_sequence(
                sample_id=record.sample_id,
                sequence_id=record.sequence_id,
                is_fall_ground_truth=record.is_fall,
                observations=observations,
                fall_onset_timestamp=onset_time,
                record=record,
            )
            results.append(res)

            if record.is_fall and res.is_fall_predicted:
                tp += 1
                if res.time_to_alert_sec is not None:
                    alert_times.append(res.time_to_alert_sec)
            elif not record.is_fall and res.is_fall_predicted:
                fp += 1
            elif not record.is_fall and not res.is_fall_predicted:
                tn += 1
            elif record.is_fall and not res.is_fall_predicted:
                fn += 1

        metrics = compute_metrics(tp=tp, fp=fp, tn=tn, fn=fn, alert_times=alert_times)
        return metrics, results
