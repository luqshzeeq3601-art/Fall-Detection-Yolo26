"""Phase 11.8 V5 Unified Real-Time Fall Detection Pipeline (P11.8-022).

Integrates:
1. 15 Hz normalized skeleton keypoint buffering (hip-centered, torso-scaled).
2. Multi-Scale temporal geometric feature extraction.
3. V5 Deep Skeleton Temporal Classifier (M2/M3).
4. ADL False-Alert Suppression.
5. PostProcessorV5 (falling -> fallen transition tracking with cooldown).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from eldercare.fall_engine.features.multiscale import (
    MultiScaleWindowConfig,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    ClassifierV5M1_HistGBDT,
    PostProcessorConfigV5,
    PostProcessorV5,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from eldercare.fall_engine.suppression.adl_suppressor import (
    ADLFalseAlertSuppressor,
    ADLSuppressionConfig,
)
from eldercare.vision.tracking.observation import TrackObservation

LOG = logging.getLogger("pipeline_v5")
ROOT = Path(__file__).resolve().parents[3]


@dataclass
class PipelineConfigV5:
    """Unified V5 Pipeline Configuration."""

    history_window_seconds: float = 2.5
    target_fps: float = 15.0
    post_processor: PostProcessorConfigV5 = field(default_factory=PostProcessorConfigV5)
    adl_suppression: ADLSuppressionConfig = field(default_factory=ADLSuppressionConfig)
    multiscale_windows: MultiScaleWindowConfig = field(default_factory=MultiScaleWindowConfig)
    model_type: str = "m2"  # "m1", "m2", "m3"
    max_track_history_length: int = 60


class FallEnginePipelineV5:
    """Production Real-Time V5 Fall Detection Pipeline."""

    def __init__(
        self,
        config: PipelineConfigV5 | None = None,
        skeleton_classifier: TemporalSkeletonClassifierV5 | None = None,
        m1_classifier: ClassifierV5M1_HistGBDT | None = None,
    ) -> None:
        self.config = config or PipelineConfigV5()
        if skeleton_classifier is not None:
            self.skeleton_classifier = skeleton_classifier
        else:
            default_m2 = ROOT / "models" / "temporal_skeleton_classifier_v5.pt"
            if default_m2.is_file():
                self.skeleton_classifier = TemporalSkeletonClassifierV5.load(default_m2)
            else:
                self.skeleton_classifier = TemporalSkeletonClassifierV5()
        self.m1_classifier = m1_classifier
        self.adl_suppressor = ADLFalseAlertSuppressor(self.config.adl_suppression)

        # Per-track state
        self._track_histories: dict[int, list[TrackObservation]] = defaultdict(list)
        self._post_processors: dict[tuple[str, int], PostProcessorV5] = {}
        self._camera_fall_candidates: dict[str, float] = {}

    def reset(self) -> None:
        """Reset all internal track state and buffers (e.g. between video sequences)."""
        self._track_histories.clear()
        self._post_processors.clear()
        self._camera_fall_candidates.clear()
        self.adl_suppressor = ADLFalseAlertSuppressor(self.config.adl_suppression)

    def _get_post_processor(self, camera_id: str, track_id: int) -> PostProcessorV5:
        key = (camera_id, track_id)
        if key not in self._post_processors:
            self._post_processors[key] = PostProcessorV5(
                config=self.config.post_processor,
                camera_id=camera_id,
                track_id=track_id,
            )
        return self._post_processors[key]

    def process_observation(
        self,
        obs: TrackObservation,
    ) -> tuple[FallState, FallEvent | None]:
        """Process a single tracked observation through V5 pipeline.

        Returns (FallState, FallEvent | None).
        """
        tid = obs.track_id
        hist = self._track_histories[tid]
        hist.append(obs)

        # Trim history
        cutoff = obs.timestamp - self.config.history_window_seconds
        while len(hist) > 1 and hist[0].timestamp < cutoff:
            hist.pop(0)
        if len(hist) > self.config.max_track_history_length:
            hist.pop(0)

        post_proc = self._get_post_processor(obs.camera_id, tid)

        # Camera-level candidate handover for tracking fragmentation
        if post_proc.fall_candidate_time is None and obs.camera_id in self._camera_fall_candidates:
            cam_t = self._camera_fall_candidates[obs.camera_id]
            if (obs.timestamp - cam_t) <= self.config.post_processor.transition_max_window_sec:
                post_proc.fall_candidate_time = cam_t

        if len(hist) < 3:
            return FallState.NORMAL, None

        # 1. Multi-scale feature extraction
        multi_feats = extract_multiscale_temporal_features(hist, self.config.multiscale_windows)

        # 2. Model Inference (M2 3-class prediction)
        p_normal, p_falling, p_fallen = self.skeleton_classifier.predict_probabilities(hist)
        p_fall_total = float(p_falling + p_fallen)

        # 3. Geometric low posture check
        aspect_floor = multi_feats.current_geometry.aspect_ratio <= 1.05
        angle_floor = multi_feats.current_geometry.torso_angle_deg <= 45.0
        is_floor = bool(
            aspect_floor
            or (multi_feats.current_geometry.aspect_ratio <= 1.30 and angle_floor)
            or p_fallen >= 0.35
        )
        is_low_posture = bool(
            is_floor or p_fallen >= self.config.post_processor.down_confirmation_threshold
        )

        # Record camera candidate if falling probability is high
        if p_falling >= self.config.post_processor.fall_trigger_threshold:
            self._camera_fall_candidates[obs.camera_id] = obs.timestamp

        # 4. ADL Suppression check (suppress intentional controlled bending/sitting)
        candidate_active = (post_proc.fall_candidate_time is not None) or (
            p_falling >= self.config.post_processor.fall_trigger_threshold
        )
        if candidate_active:
            supp_res = self.adl_suppressor.evaluate_suppression(
                multi_feats, hist, classifier_probability=p_fall_total
            )
            if supp_res.suppressed and supp_res.reason.value != "CLASSIFIER_VETO":
                if not is_floor:
                    post_proc.reset()
                    return FallState.NORMAL, None

        # 5. PostProcessor state update
        alert_triggered = post_proc.update(
            timestamp=obs.timestamp,
            p_falling=p_falling,
            p_fallen=p_fallen,
            is_low_posture=is_low_posture,
        )

        if alert_triggered:
            cand_t = (
                post_proc.fall_candidate_time
                if post_proc.fall_candidate_time is not None
                else obs.timestamp
            )
            down_t = (
                post_proc.down_start_time
                if post_proc.down_start_time is not None
                else obs.timestamp
            )
            event = FallEvent(
                camera_id=obs.camera_id,
                track_id=tid,
                confirmed_timestamp=obs.timestamp,
                candidate_timestamp=cand_t,
                down_start_timestamp=down_t,
                features=multi_feats.medium_features
                if hasattr(multi_feats, "medium_features")
                else None,  # type: ignore
                confidence=p_fall_total,
                reason="Sustained low posture after fall transition",
            )
            return FallState.FALL_CONFIRMED, event

        if post_proc.fall_candidate_time is not None:
            if is_low_posture:
                return FallState.DOWN_CONFIRMING, None
            return FallState.DESCENT_CANDIDATE, None
        elif p_falling >= self.config.post_processor.fall_trigger_threshold:
            return FallState.DESCENT_CANDIDATE, None
        else:
            return FallState.NORMAL, None
