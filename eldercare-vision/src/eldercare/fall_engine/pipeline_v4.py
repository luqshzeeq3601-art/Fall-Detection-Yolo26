# ruff: noqa: E501
"""Unified End-to-End V4 Fall Detection Pipeline (Phase 11.7 P11.7-014).

Integrates multi-scale temporal windowing, camera perspective normalizer,
recurrent temporal classifier (GRUClassifierV4), complex ADL false alert suppressor,
and track state machine into a cohesive real-time inference engine.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig, IncidentCooldownManager
from eldercare.fall_engine.learned_classifier.classifier_v4 import (
    GRUClassifierV4,
    LogisticClassifierV4,
    TemporalClassifierV4Base,
)
from eldercare.fall_engine.normalization.camera_normalizer import (
    CameraNormalizationConfig,
    CameraPerspectiveNormalizer,
)
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import TrackFallStateMachineV3
from eldercare.fall_engine.suppression.adl_suppressor import (
    ADLFalseAlertSuppressor,
    ADLSuppressionConfig,
)
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass
class FallEnginePipelineV4:
    """Unified production pipeline for ElderCare Vision V4 Fall Detection."""

    config: FallStateMachineConfigV3 = field(default_factory=FallStateMachineConfigV3)
    camera_config: CameraNormalizationConfig = field(default_factory=CameraNormalizationConfig)
    suppression_config: ADLSuppressionConfig = field(default_factory=ADLSuppressionConfig)
    confidence_config: FallConfidenceConfig = field(default_factory=FallConfidenceConfig)

    classifier: TemporalClassifierV4Base | Any | None = None
    camera_normalizer: CameraPerspectiveNormalizer = field(init=False)
    adl_suppressor: ADLFalseAlertSuppressor = field(init=False)
    cooldown_manager: IncidentCooldownManager = field(init=False)

    # Per-track state machines keyed by (camera_id, track_id)
    _state_machines: dict[tuple[str, int], TrackFallStateMachineV3] = field(
        default_factory=dict, init=False
    )
    # Bounded history buffers per track
    _track_histories: dict[tuple[str, int], list[TrackObservation]] = field(
        default_factory=lambda: defaultdict(list), init=False
    )
    max_history_seconds: float = 3.0

    def __post_init__(self) -> None:
        self.camera_normalizer = CameraPerspectiveNormalizer(self.camera_config)
        self.adl_suppressor = ADLFalseAlertSuppressor(self.suppression_config)
        cooldown_cfg = CooldownConfig(
            incident_cooldown_sec=self.config.recovery_cooldown_sec,
            camera_cooldown_sec=0.5,
        )
        self.cooldown_manager = IncidentCooldownManager(config=cooldown_cfg)
        if self.classifier is None and self.config.use_learned_classifier:
            self.classifier = self._load_default_classifier()

    def _load_default_classifier(self) -> TemporalClassifierV4Base | None:
        """Load default V4 classifier weights."""
        candidates = [
            Path("models/temporal_fall_classifier_v4.json"),
            Path("eldercare-vision/models/temporal_fall_classifier_v4.json"),
            Path(__file__).resolve().parents[4] / "models" / "temporal_fall_classifier_v4.json",
            Path(__file__).resolve().parents[3] / "models" / "temporal_fall_classifier_v4.json",
        ]
        for p in candidates:
            if p.is_file():
                try:
                    return GRUClassifierV4.load(p)
                except Exception:
                    try:
                        return LogisticClassifierV4.load(p)
                    except Exception:
                        pass
        return None

    def _get_or_create_state_machine(self, camera_id: str, track_id: int) -> TrackFallStateMachineV3:
        key = (camera_id, track_id)
        if key not in self._state_machines:
            sm = TrackFallStateMachineV3(
                camera_id=camera_id,
                track_id=track_id,
                config=self.config,
                confidence_config=self.confidence_config,
                cooldown_manager=self.cooldown_manager,
                classifier=self.classifier,
            )
            sm.adl_suppressor = self.adl_suppressor
            self._state_machines[key] = sm
        return self._state_machines[key]

    def process_observation(self, obs: TrackObservation) -> tuple[FallState, FallEvent | None]:
        """Process a single tracked person observation through the V4 pipeline.

        Args:
            obs: TrackObservation domain contract instance.

        Returns:
            Tuple of (current FallState, optional emitted FallEvent).
        """
        if obs.track_id is None:
            return FallState.NORMAL, None

        key = (obs.camera_id, obs.track_id)
        history = self._track_histories[key]

        # Optional camera perspective rectification on keypoints
        if self.camera_config.enabled and abs(self.camera_config.camera_pitch_deg) > 1.0:
            rectified_kpts = self.camera_normalizer.rectify_keypoints(
                obs.keypoints,
                image_width_px=float(obs.image_width),
                image_height_px=float(obs.image_height),
            )
            # Reconstruct observation with rectified keypoints
            obs = TrackObservation(
                camera_id=obs.camera_id,
                track_id=obs.track_id,
                timestamp=obs.timestamp,
                bbox_xyxy=obs.bbox_xyxy,
                detection_confidence=obs.detection_confidence,
                keypoints=rectified_kpts,
                image_width=obs.image_width,
                image_height=obs.image_height,
            )

        history.append(obs)

        # Prune old observations beyond max_history_seconds
        cutoff = obs.timestamp - self.max_history_seconds
        while len(history) > 1 and history[0].timestamp < cutoff:
            history.pop(0)

        sm = self._get_or_create_state_machine(obs.camera_id, obs.track_id)
        state, event = sm.update(history)

        return state, event

    def process_frame_observations(
        self,
        observations: Sequence[TrackObservation],
    ) -> list[tuple[int, FallState, FallEvent | None]]:
        """Process all tracked individuals in a frame.

        Args:
            observations: Sequence of TrackObservations for the active frame.

        Returns:
            List of tuples: (track_id, current FallState, optional FallEvent).
        """
        results = []
        for obs in observations:
            if obs.track_id is not None:
                st, ev = self.process_observation(obs)
                results.append((obs.track_id, st, ev))
        return results

    def reset_track(self, camera_id: str, track_id: int) -> None:
        """Reset state machine and history buffer for a lost/expired track."""
        key = (camera_id, track_id)
        self._state_machines.pop(key, None)
        self._track_histories.pop(key, None)

    def reset_all(self) -> None:
        """Reset all active tracks and state machines across all cameras."""
        self._state_machines.clear()
        self._track_histories.clear()
