"""Enhanced Fall state machine v2 implementation for tracked individuals (Phase 11.5)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from eldercare.fall_engine.confidence.calculator import (
    FallConfidenceBreakdown,
    FallConfidenceConfig,
)
from eldercare.fall_engine.confidence.cooldown import IncidentCooldownManager
from eldercare.fall_engine.features.motion_v2 import (
    TemporalFeaturesV2,
    extract_temporal_features_v2,
)
from eldercare.fall_engine.learned_classifier.classifier import LearnedTemporalFallClassifier
from eldercare.fall_engine.state_machine.states import (
    FallEvent,
    FallState,
    FallStateTransition,
)
from eldercare.fall_engine.state_machine_v2.config_v2 import FallStateMachineConfigV2
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass
class TrackFallStateMachineV2:
    """State machine tracking fall progression v2 with scale-normalization and learned scoring."""

    camera_id: str
    track_id: int
    config: FallStateMachineConfigV2 = field(default_factory=FallStateMachineConfigV2)
    confidence_config: FallConfidenceConfig = field(default_factory=FallConfidenceConfig)
    cooldown_manager: IncidentCooldownManager | None = None
    classifier: LearnedTemporalFallClassifier | None = field(
        default_factory=LearnedTemporalFallClassifier
    )

    state: FallState = FallState.NORMAL
    state_entry_timestamp: float = 0.0
    candidate_timestamp: float | None = None
    candidate_features: TemporalFeaturesV2 | None = None
    down_start_timestamp: float | None = None
    down_frame_count: int = 0
    confirmed_event: FallEvent | None = None
    last_observation_timestamp: float = 0.0
    transitions: list[FallStateTransition] = field(default_factory=list)

    def _is_low_posture(self, feats: TemporalFeaturesV2) -> bool:
        """Check if current geometry indicates a horizontal or ground-level posture."""
        geom = feats.current_geometry
        aspect_low = geom.aspect_ratio <= self.config.fallen_aspect_ratio_max
        angle_low = geom.torso_angle_deg <= self.config.fallen_torso_angle_max_deg
        hip_low = geom.hip_height_ratio >= 0.55  # Hip near bottom half of bbox

        if self.config.use_learned_classifier and self.classifier is not None:
            prob = self.classifier.predict_probability(feats)
            if prob >= self.config.classifier_confirmation_threshold:
                return True

        return (aspect_low or angle_low) and hip_low

    def _is_upright_posture(self, feats: TemporalFeaturesV2) -> bool:
        """Check if current geometry indicates an upright posture."""
        geom = feats.current_geometry
        return bool(
            geom.aspect_ratio >= self.config.recovery_aspect_ratio_min
            and geom.torso_angle_deg >= self.config.recovery_torso_angle_min_deg
        )

    def _is_rapid_descent(self, feats: TemporalFeaturesV2) -> bool:
        """Check if motion dynamics indicate a rapid descent."""
        peak_vel_trigger = (
            feats.scale_normalized_peak_velocity >= self.config.peak_descent_velocity_threshold
        )
        avg_vel_trigger = (
            feats.scale_normalized_vertical_velocity >= self.config.descent_velocity_threshold
        )
        ratio_drop_trigger = (
            feats.aspect_ratio_relative_change <= self.config.descent_aspect_ratio_drop
            and feats.scale_normalized_vertical_velocity > 0.25
        )

        classifier_trigger = False
        if self.config.use_learned_classifier and self.classifier is not None:
            prob = self.classifier.predict_probability(feats)
            classifier_trigger = prob >= self.config.classifier_trigger_threshold

        return peak_vel_trigger or avg_vel_trigger or ratio_drop_trigger or classifier_trigger

    def _transition_to(
        self,
        new_state: FallState,
        timestamp: float,
        reason: str,
        feats: Any = None,
    ) -> None:
        """Record and apply a state transition."""
        trans = FallStateTransition(
            from_state=self.state,
            to_state=new_state,
            timestamp=timestamp,
            reason=reason,
            features_snapshot=None,  # V1 snapshot compatibility
        )
        self.transitions.append(trans)
        logger.debug(
            "Track V2 (%s, %d) transition %s -> %s at %.3fs: %s",
            self.camera_id,
            self.track_id,
            self.state.value,
            new_state.value,
            timestamp,
            reason,
        )
        self.state = new_state
        self.state_entry_timestamp = timestamp

    def update(self, history: Sequence[TrackObservation]) -> tuple[FallState, FallEvent | None]:
        """Process latest track observation history and update state machine v2.

        Args:
            history: Non-empty sequence of TrackObservation for this person.

        Returns:
            Tuple of (current_state, newly_confirmed_fall_event_or_None).
        """
        if not history:
            return self.state, None

        feats = extract_temporal_features_v2(history, window_seconds=self.config.feature_window_sec)
        current_time = float(history[-1].timestamp)
        self.last_observation_timestamp = current_time
        emitted_event: FallEvent | None = None

        if self.state == FallState.NORMAL:
            if self._is_rapid_descent(feats):
                self.candidate_timestamp = current_time
                self.candidate_features = feats
                self.down_frame_count = 1 if self._is_low_posture(feats) else 0
                self._transition_to(
                    FallState.DESCENT_CANDIDATE,
                    current_time,
                    f"Rapid descent v2: peak_vel={feats.scale_normalized_peak_velocity:.2f}h/s, "
                    f"aspect_rel_delta={feats.aspect_ratio_relative_change:.2f}",
                    feats,
                )

        elif self.state == FallState.DESCENT_CANDIDATE:
            cand_time = self.candidate_timestamp or current_time
            if (current_time - cand_time) > self.config.descent_candidate_timeout_sec:
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_frame_count = 0
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Descent candidate timed out without sustaining low posture",
                    feats,
                )
            elif self._is_low_posture(feats):
                self.down_frame_count += 1
                if self.down_frame_count >= self.config.min_down_confirming_frames:
                    self.down_start_timestamp = current_time
                    self._transition_to(
                        FallState.DOWN_CONFIRMING,
                        current_time,
                        f"Down posture confirmed across {self.down_frame_count} frames",
                        feats,
                    )
            else:
                if self._is_upright_posture(feats):
                    self.candidate_timestamp = None
                    self.candidate_features = None
                    self.down_frame_count = 0
                    self._transition_to(
                        FallState.NORMAL,
                        current_time,
                        "Candidate aborted: upright posture restored",
                        feats,
                    )

        elif self.state == FallState.DOWN_CONFIRMING:
            if self._is_upright_posture(feats):
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_start_timestamp = None
                self.down_frame_count = 0
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Down confirmation aborted: person recovered upright",
                    feats,
                )
            elif self._is_low_posture(feats):
                down_time = self.down_start_timestamp or current_time
                if (current_time - down_time) >= self.config.down_confirmation_sec:
                    dur = current_time - down_time
                    # Calculate composite confidence
                    classifier_prob = 0.85
                    if self.config.use_learned_classifier and self.classifier is not None:
                        classifier_prob = self.classifier.predict_probability(feats)

                    confidence_val = min(
                        1.0,
                        max(
                            0.5,
                            0.5 * classifier_prob
                            + 0.3 * (1.0 - min(1.0, feats.current_geometry.aspect_ratio / 1.5))
                            + 0.2 * feats.current_geometry.keypoint_confidence_mean,
                        ),
                    )

                    breakdown = FallConfidenceBreakdown(
                        composite_confidence=round(confidence_val, 4),
                        motion_score=round(min(1.0, feats.scale_normalized_peak_velocity / 1.0), 4),
                        posture_score=round(
                            max(0.0, 1.0 - feats.current_geometry.aspect_ratio / 1.2), 4
                        ),
                        persistence_score=round(min(1.0, dur / 1.5), 4),
                        missing_keypoint_penalty=0.0,
                        unstable_track_penalty=0.0,
                        average_pose_confidence=round(
                            feats.current_geometry.keypoint_confidence_mean, 4
                        ),
                        key_contributing_features={
                            "scale_norm_peak_vel": round(feats.scale_normalized_peak_velocity, 3),
                            "aspect_ratio": round(feats.current_geometry.aspect_ratio, 3),
                            "torso_angle": round(feats.current_geometry.torso_angle_deg, 1),
                            "classifier_prob": round(classifier_prob, 3),
                        },
                        config_version="2.0.0",
                    )

                    event = FallEvent(
                        camera_id=self.camera_id,
                        track_id=self.track_id,
                        confirmed_timestamp=current_time,
                        candidate_timestamp=self.candidate_timestamp or current_time,
                        down_start_timestamp=down_time,
                        features=None,
                        confidence=breakdown.composite_confidence,
                        reason="Down posture sustained after rapid descent (v2 engine)",
                        confidence_breakdown=breakdown,
                    )
                    self.confirmed_event = event

                    if self.cooldown_manager is not None:
                        if not self.cooldown_manager.is_in_cooldown(
                            self.camera_id, self.track_id, current_time
                        ):
                            self.cooldown_manager.record_incident(
                                self.camera_id, self.track_id, current_time
                            )
                            emitted_event = event
                        else:
                            logger.info(
                                "Fall event suppressed by cooldown for track (%s, %d) at %.3fs",
                                self.camera_id,
                                self.track_id,
                                current_time,
                            )
                    else:
                        emitted_event = event

                    self._transition_to(
                        FallState.FALL_CONFIRMED,
                        current_time,
                        f"Fall confirmed v2 (conf={breakdown.composite_confidence:.2f}): "
                        f"sustained low posture for {dur:.2f}s",
                        feats,
                    )

        elif self.state == FallState.FALL_CONFIRMED:
            if self._is_upright_posture(feats):
                self._transition_to(
                    FallState.RECOVERY,
                    current_time,
                    "Recovery started: upright posture detected",
                    feats,
                )

        elif self.state == FallState.RECOVERY:
            if self._is_rapid_descent(feats):
                self.candidate_timestamp = current_time
                self.candidate_features = feats
                self.down_frame_count = 1 if self._is_low_posture(feats) else 0
                self._transition_to(
                    FallState.DESCENT_CANDIDATE,
                    current_time,
                    "Re-fall detected during recovery",
                    feats,
                )
            elif (current_time - self.state_entry_timestamp) >= self.config.recovery_cooldown_sec:
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_start_timestamp = None
                self.down_frame_count = 0
                self.confirmed_event = None
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Recovery cooldown completed",
                    feats,
                )

        return self.state, emitted_event

    def reset(self) -> None:
        """Reset state machine to initial NORMAL state."""
        self.state = FallState.NORMAL
        self.state_entry_timestamp = 0.0
        self.candidate_timestamp = None
        self.candidate_features = None
        self.down_start_timestamp = None
        self.down_frame_count = 0
        self.confirmed_event = None
        self.last_observation_timestamp = 0.0
        self.transitions.clear()


class FallStateMachineManagerV2:
    """Manages per-person FallStateMachineV2 instances across multiple camera tracks."""

    def __init__(
        self,
        config: FallStateMachineConfigV2 | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_manager: IncidentCooldownManager | None = None,
        classifier: LearnedTemporalFallClassifier | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfigV2()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_manager = cooldown_manager
        self.classifier = classifier or LearnedTemporalFallClassifier()
        self._machines: dict[tuple[str, int], TrackFallStateMachineV2] = {}

    def get_machine(self, camera_id: str, track_id: int) -> TrackFallStateMachineV2:
        """Get or create state machine for (camera_id, track_id)."""
        key = (camera_id, track_id)
        if key not in self._machines:
            self._machines[key] = TrackFallStateMachineV2(
                camera_id=camera_id,
                track_id=track_id,
                config=self.config,
                confidence_config=self.confidence_config,
                cooldown_manager=self.cooldown_manager,
                classifier=self.classifier,
            )
        return self._machines[key]

    def update_track(
        self,
        camera_id: str,
        track_id: int,
        history: Sequence[TrackObservation],
    ) -> tuple[FallState, FallEvent | None]:
        """Update state machine for a track."""
        machine = self.get_machine(camera_id, track_id)
        return machine.update(history)

    def get_state(self, camera_id: str, track_id: int) -> FallState:
        """Get state for track, or NORMAL if not found."""
        key = (camera_id, track_id)
        machine = self._machines.get(key)
        return machine.state if machine is not None else FallState.NORMAL

    def cleanup_expired_tracks(self, active_keys: set[tuple[str, int]]) -> int:
        """Remove state machines for expired tracks."""
        all_keys = list(self._machines.keys())
        removed = 0
        for key in all_keys:
            if key not in active_keys:
                del self._machines[key]
                removed += 1
        return removed

    @property
    def active_tracks_count(self) -> int:
        """Count of active track state machines."""
        return len(self._machines)
