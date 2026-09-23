"""Fall state machine implementation for tracked individuals."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from eldercare.fall_engine.confidence.calculator import (
    FallConfidenceConfig,
    compute_fall_confidence,
)
from eldercare.fall_engine.confidence.cooldown import IncidentCooldownManager
from eldercare.fall_engine.features.motion import TemporalFeatures, extract_temporal_features
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from eldercare.fall_engine.state_machine.states import (
    FallEvent,
    FallState,
    FallStateTransition,
)
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


@dataclass
class TrackFallStateMachine:
    """State machine tracking fall progression for a single person track."""

    camera_id: str
    track_id: int
    config: FallStateMachineConfig = field(default_factory=FallStateMachineConfig)
    confidence_config: FallConfidenceConfig = field(default_factory=FallConfidenceConfig)
    cooldown_manager: IncidentCooldownManager | None = None

    state: FallState = FallState.NORMAL
    state_entry_timestamp: float = 0.0
    candidate_timestamp: float | None = None
    candidate_features: TemporalFeatures | None = None
    down_start_timestamp: float | None = None
    down_frame_count: int = 0
    confirmed_event: FallEvent | None = None
    last_observation_timestamp: float = 0.0
    transitions: list[FallStateTransition] = field(default_factory=list)

    def _is_low_posture(self, feats: TemporalFeatures) -> bool:
        """Check if current geometry indicates a horizontal or collapsed low posture."""
        geom = feats.current_geometry
        return bool(
            geom.aspect_ratio <= self.config.fallen_aspect_ratio_max
            or geom.torso_angle_deg <= self.config.fallen_torso_angle_max_deg
        )

    def _is_upright_posture(self, feats: TemporalFeatures) -> bool:
        """Check if current geometry indicates an upright posture."""
        geom = feats.current_geometry
        return bool(
            geom.aspect_ratio >= self.config.recovery_aspect_ratio_min
            and geom.torso_angle_deg >= self.config.recovery_torso_angle_min_deg
        )

    def _is_rapid_descent(self, feats: TemporalFeatures) -> bool:
        """Check if motion dynamics indicate a sudden downward collapse."""
        peak_vel_trigger = (
            feats.normalized_peak_vertical_velocity >= self.config.peak_descent_velocity_threshold
        )
        avg_vel_trigger = (
            feats.normalized_vertical_velocity >= self.config.descent_velocity_threshold
        )
        ratio_drop_trigger = (
            feats.aspect_ratio_change <= self.config.descent_aspect_ratio_drop
            and feats.normalized_vertical_velocity > 0.3
        )
        return peak_vel_trigger or avg_vel_trigger or ratio_drop_trigger

    def _transition_to(
        self,
        new_state: FallState,
        timestamp: float,
        reason: str,
        feats: TemporalFeatures | None = None,
    ) -> None:
        """Record and apply a state transition."""
        trans = FallStateTransition(
            from_state=self.state,
            to_state=new_state,
            timestamp=timestamp,
            reason=reason,
            features_snapshot=feats,
        )
        self.transitions.append(trans)
        logger.debug(
            "Track (%s, %d) transition %s -> %s at %.3fs: %s",
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
        """Process latest track observation history and update state.

        Args:
            history: Non-empty sequence of TrackObservation for this person.

        Returns:
            Tuple of (current_state, newly_confirmed_fall_event_or_None).
        """
        if not history:
            return self.state, None

        feats = extract_temporal_features(history, window_seconds=self.config.feature_window_sec)
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
                    f"Rapid descent: peak_vel={feats.normalized_peak_vertical_velocity:.2f}, "
                    f"aspect_delta={feats.aspect_ratio_change:.2f}",
                    feats,
                )

        elif self.state == FallState.DESCENT_CANDIDATE:
            cand_time = self.candidate_timestamp or current_time
            if (current_time - cand_time) > self.config.descent_candidate_timeout_sec:
                # Timed out without reaching down confirmation
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_frame_count = 0
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Descent candidate timed out without sustaining down posture",
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
                # If person rapidly stands back upright, cancel candidate
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
                # Stood back up before confirmation period completed
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
                    breakdown = compute_fall_confidence(
                        feats,
                        history,
                        down_duration_seconds=dur,
                        config=self.confidence_config,
                        candidate_features=self.candidate_features,
                    )

                    event = FallEvent(
                        camera_id=self.camera_id,
                        track_id=self.track_id,
                        confirmed_timestamp=current_time,
                        candidate_timestamp=self.candidate_timestamp or current_time,
                        down_start_timestamp=down_time,
                        features=feats,
                        confidence=breakdown.composite_confidence,
                        reason="Down posture sustained after rapid descent",
                        confidence_breakdown=breakdown,
                    )
                    self.confirmed_event = event

                    # Check cooldown if manager attached
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
                        f"Fall confirmed (conf={breakdown.composite_confidence:.2f}): "
                        f"sustained low posture for {dur:.2f}s",
                        feats,
                    )

        elif self.state == FallState.FALL_CONFIRMED:
            # Person remains in FALL_CONFIRMED without re-alerting unless recovery occurs
            if self._is_upright_posture(feats):
                self._transition_to(
                    FallState.RECOVERY,
                    current_time,
                    "Recovery started: upright posture detected",
                    feats,
                )

        elif self.state == FallState.RECOVERY:
            # Check for re-fall during recovery
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
                # Cooldown completed, return to NORMAL
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


class FallStateMachineManager:
    """Manages per-person FallStateMachine instances across multiple camera tracks."""

    def __init__(
        self,
        config: FallStateMachineConfig | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_manager: IncidentCooldownManager | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfig()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_manager = cooldown_manager
        self._machines: dict[tuple[str, int], TrackFallStateMachine] = {}

    def get_machine(self, camera_id: str, track_id: int) -> TrackFallStateMachine:
        """Get or create the state machine for a (camera_id, track_id) track."""
        key = (camera_id, track_id)
        if key not in self._machines:
            self._machines[key] = TrackFallStateMachine(
                camera_id=camera_id,
                track_id=track_id,
                config=self.config,
                confidence_config=self.confidence_config,
                cooldown_manager=self.cooldown_manager,
            )
        return self._machines[key]

    def update_track(
        self,
        camera_id: str,
        track_id: int,
        history: Sequence[TrackObservation],
    ) -> tuple[FallState, FallEvent | None]:
        """Update the state machine for a specific track observation history."""
        machine = self.get_machine(camera_id, track_id)
        return machine.update(history)

    def get_state(self, camera_id: str, track_id: int) -> FallState:
        """Get the current state for a track, or NORMAL if not found."""
        key = (camera_id, track_id)
        machine = self._machines.get(key)
        return machine.state if machine is not None else FallState.NORMAL

    def cleanup_expired_tracks(self, active_keys: set[tuple[str, int]]) -> int:
        """Remove state machines for tracks that are no longer active.

        Args:
            active_keys: Set of (camera_id, track_id) tuples currently tracked.

        Returns:
            Number of expired track state machines removed.
        """
        all_keys = list(self._machines.keys())
        removed = 0
        for key in all_keys:
            if key not in active_keys:
                del self._machines[key]
                removed += 1
        return removed

    @property
    def active_tracks_count(self) -> int:
        """Number of active per-track state machines currently stored."""
        return len(self._machines)
