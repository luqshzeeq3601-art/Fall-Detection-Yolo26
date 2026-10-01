"""Sequence evaluation runner for Fall Engine v3."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig, IncidentCooldownManager
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.evaluation.metrics_v3 import (
    DeploymentMetricsV3,
    V3EvaluationResult,
    compute_deployment_metrics_v3,
)
from eldercare.fall_engine.features.features_v3 import extract_geometry_features_v3
from eldercare.fall_engine.learned_classifier.classifier_v3 import TemporalClassifierV3Base
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import (
    TrackFallStateMachineV3,
    _get_default_v3_classifier,
)
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


class SequenceEvaluationRunnerV3:
    """Executes sequence evaluation over TrackObservation streams using Fall Engine v3."""

    def __init__(
        self,
        config: FallStateMachineConfigV3 | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_config: CooldownConfig | None = None,
        classifier: TemporalClassifierV3Base | Any | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfigV3()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_config = cooldown_config or CooldownConfig()
        self.classifier = classifier if classifier is not None else _get_default_v3_classifier()

    def evaluate_sequence(
        self,
        observations: Sequence[TrackObservation],
        ground_truth_is_fall: bool,
        ground_truth_onset_sec: float | None = None,
        sample_id: str = "unknown",
        sequence_id: str = "unknown",
        record: SequenceManifestRecord | None = None,
    ) -> tuple[V3EvaluationResult, Any]:
        """Evaluate a single sequence with Fall Engine v3."""
        cooldown_mgr = IncidentCooldownManager(config=self.cooldown_config)
        sm = TrackFallStateMachineV3(
            camera_id="eval_cam",
            track_id=1,
            config=self.config,
            confidence_config=self.confidence_config,
            cooldown_manager=cooldown_mgr,
            classifier=self.classifier,
        )

        history: list[TrackObservation] = []
        confirmed_event = None
        time_to_alert_ms = None

        total_frames_in_fall_window = 0
        frames_with_usable_pose = 0
        continuous_track_frames = 0
        expected_track_frames = len(observations)
        id_switches = 0

        last_track_id = None
        last_time = None

        for obs in observations:
            if last_track_id is not None and obs.track_id != last_track_id:
                id_switches += 1
            last_track_id = obs.track_id

            if last_time is not None:
                if obs.timestamp - last_time <= 0.2:
                    continuous_track_frames += 1
            last_time = obs.timestamp

            if ground_truth_onset_sec is not None and obs.timestamp >= ground_truth_onset_sec:
                total_frames_in_fall_window += 1
                try:
                    geom = extract_geometry_features_v3(obs)
                    if geom.keypoints_present_count >= 8:
                        frames_with_usable_pose += 1
                except Exception:
                    pass

            history.append(obs)
            _, event = sm.update(history)
            if event is not None and confirmed_event is None:
                confirmed_event = event
                if ground_truth_onset_sec is not None:
                    tta = max(0.0, event.confirmed_timestamp - ground_truth_onset_sec)
                    time_to_alert_ms = tta * 1000.0

        is_fall_predicted = confirmed_event is not None

        tp = is_fall_predicted and ground_truth_is_fall
        fp = is_fall_predicted and not ground_truth_is_fall
        fn = not is_fall_predicted and ground_truth_is_fall
        tn = not is_fall_predicted and not ground_truth_is_fall

        duration_hours = 0.0
        if observations:
            duration_hours = (observations[-1].timestamp - observations[0].timestamp) / 3600.0

        result = V3EvaluationResult(
            is_true_positive=tp,
            is_false_positive=fp,
            is_false_negative=fn,
            is_true_negative=tn,
            probability=confirmed_event.confidence if confirmed_event else None,
            non_fall_duration_hours=duration_hours if not ground_truth_is_fall else 0.0,
            time_to_alert_ms=time_to_alert_ms if tp else None,
            total_frames_in_fall_window=total_frames_in_fall_window,
            frames_with_usable_pose=frames_with_usable_pose,
            expected_track_frames=expected_track_frames,
            continuous_track_frames=continuous_track_frames,
            id_switches=id_switches,
        )

        return result, confirmed_event

    def evaluate_batch(
        self,
        items: Sequence[tuple[SequenceManifestRecord, Sequence[TrackObservation], float | None]],
    ) -> tuple[DeploymentMetricsV3, list[V3EvaluationResult]]:
        """Evaluate a batch of sequence tuples."""
        results: list[V3EvaluationResult] = []
        for record, obs_seq, onset_sec in items:
            res, _ = self.evaluate_sequence(
                observations=obs_seq,
                ground_truth_is_fall=record.is_fall,
                ground_truth_onset_sec=onset_sec,
                sample_id=record.sample_id,
                sequence_id=record.sequence_id,
                record=record,
            )
            results.append(res)

        metrics = compute_deployment_metrics_v3(results, fps=30.0)
        return metrics, results
