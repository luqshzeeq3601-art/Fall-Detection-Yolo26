# ruff: noqa: E501
"""Enhanced Fall state machine v3 implementation for tracked individuals."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eldercare.fall_engine.confidence.calculator import (
    FallConfidenceBreakdown,
    FallConfidenceConfig,
)
from eldercare.fall_engine.confidence.cooldown import IncidentCooldownManager
from eldercare.fall_engine.features.features_v3 import (
    TemporalFeaturesV3,
    extract_temporal_features_v3,
)
from eldercare.fall_engine.features.multiscale import (
    MultiScaleTemporalFeatures,
    MultiScaleWindowConfig,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.classifier_v3 import (
    LogisticClassifierV3,
    TemporalClassifierV3Base,
)
from eldercare.fall_engine.state_machine.states import (
    FallEvent,
    FallState,
    FallStateTransition,
)
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.suppression.adl_suppressor import ADLFalseAlertSuppressor
from eldercare.fall_engine.tracking_v3 import TrackStitchConfig, TrackStitcher
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


def _get_default_v3_classifier() -> Any | None:
    """Load default V4 or V3 classifier weights if available on disk."""
    try:
        from eldercare.fall_engine.learned_classifier.classifier_v4 import (
            GRUClassifierV4,
            LogisticClassifierV4,
            TemporalClassifierV4Base,
        )
        TemporalClassifierV3Base.register(TemporalClassifierV4Base)
        candidates_v4 = [
            Path("models/temporal_fall_classifier_v4.json"),
            Path("eldercare-vision/models/temporal_fall_classifier_v4.json"),
            Path(__file__).resolve().parents[4] / "models" / "temporal_fall_classifier_v4.json",
            Path(__file__).resolve().parents[3] / "models" / "temporal_fall_classifier_v4.json",
        ]
        for p in candidates_v4:
            if p.is_file():
                try:
                    return GRUClassifierV4.load(p)
                except Exception:
                    try:
                        return LogisticClassifierV4.load(p)
                    except Exception:
                        pass
    except Exception:
        pass

    candidates = [
        Path("models/temporal_fall_classifier_v3.json"),
        Path("eldercare-vision/models/temporal_fall_classifier_v3.json"),
        Path(__file__).resolve().parents[4] / "models" / "temporal_fall_classifier_v3.json",
        Path(__file__).resolve().parents[3] / "models" / "temporal_fall_classifier_v3.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return LogisticClassifierV3.load(p)
            except Exception as e:
                logger.warning("Failed to load V3 classifier from %s: %s", p, e)
    return None


@dataclass
class TrackFallStateMachineV3:
    """State machine tracking fall progression v3 with V3 features and tracking gap awareness."""

    camera_id: str
    track_id: int
    config: FallStateMachineConfigV3 = field(default_factory=FallStateMachineConfigV3)
    confidence_config: FallConfidenceConfig = field(default_factory=FallConfidenceConfig)
    cooldown_manager: IncidentCooldownManager | None = None
    classifier: TemporalClassifierV3Base | Any | None = field(
        default_factory=_get_default_v3_classifier
    )
    adl_suppressor: ADLFalseAlertSuppressor = field(
        default_factory=ADLFalseAlertSuppressor
    )

    state: FallState = FallState.NORMAL
    state_entry_timestamp: float = 0.0
    candidate_timestamp: float | None = None
    candidate_features: TemporalFeaturesV3 | MultiScaleTemporalFeatures | None = None
    down_start_timestamp: float | None = None
    down_frame_count: int = 0
    confirmed_event: FallEvent | None = None
    last_observation_timestamp: float = 0.0
    transitions: list[FallStateTransition] = field(default_factory=list)

    def _is_low_posture(self, feats: TemporalFeaturesV3 | MultiScaleTemporalFeatures) -> bool:
        """Check if current geometry indicates a horizontal or ground-level posture."""
        geom = feats.current_geometry

        # If geometry is clearly upright, it cannot be a low posture
        if (
            geom.aspect_ratio >= self.config.recovery_aspect_ratio_min
            and geom.torso_angle_deg >= self.config.recovery_torso_angle_min_deg
        ):
            return False

        aspect_low = geom.aspect_ratio <= self.config.fallen_aspect_ratio_max
        angle_low = geom.torso_angle_deg <= self.config.fallen_torso_angle_max_deg
        hip_low = geom.hip_height_ratio >= 0.55  # Hip near bottom half of bbox
        floor_prox_low = feats.floor_proximity_ratio < 0.25

        geometric_low = (aspect_low or angle_low) and (hip_low or floor_prox_low)

        if self.config.use_learned_classifier and self.classifier is not None:
            try:
                prob = self.classifier.predict_probability(feats.feature_vector)
                if prob >= self.config.classifier_confirmation_threshold:
                    return True
            except Exception as e:
                logger.debug("Classifier probability check failed in low posture: %s", e)

        return geometric_low

    def _is_upright_posture(self, feats: TemporalFeaturesV3 | MultiScaleTemporalFeatures) -> bool:
        """Check if current geometry indicates an upright posture."""
        geom = feats.current_geometry
        return bool(
            geom.aspect_ratio >= self.config.recovery_aspect_ratio_min
            and geom.torso_angle_deg >= self.config.recovery_torso_angle_min_deg
        )

    def _is_rapid_descent(self, feats: TemporalFeaturesV3 | MultiScaleTemporalFeatures) -> bool:
        """Check if motion dynamics indicate a rapid descent across single or multi-scale windows."""
        if isinstance(feats, MultiScaleTemporalFeatures):
            peak_vel = feats.max_scale_normalized_peak_velocity
            avg_vel = feats.max_scale_normalized_vertical_velocity
            rel_change = feats.min_aspect_ratio_relative_change
            ang_vel = feats.max_angular_velocity_deg_per_sec
            cent_acc = feats.max_centroid_acceleration
            feat_vec = feats.fused_feature_vector
        else:
            peak_vel = feats.scale_normalized_peak_velocity
            avg_vel = feats.scale_normalized_vertical_velocity
            rel_change = feats.aspect_ratio_relative_change
            ang_vel = feats.angular_velocity_deg_per_sec
            cent_acc = feats.centroid_acceleration
            feat_vec = feats.feature_vector

        peak_vel_trigger = peak_vel >= self.config.peak_descent_velocity_threshold
        avg_vel_trigger = avg_vel >= self.config.descent_velocity_threshold
        ratio_drop_trigger = (
            rel_change <= self.config.descent_aspect_ratio_drop
            and avg_vel > 0.25
        )

        angular_vel_trigger = False
        if self.config.use_angular_velocity:
            angular_vel_trigger = (
                abs(ang_vel) >= self.config.angular_velocity_descent_threshold
                and cent_acc > 0.1
            )

        classifier_trigger = False
        if self.config.use_learned_classifier and self.classifier is not None:
            try:
                prob = self.classifier.predict_probability(feat_vec)
                classifier_trigger = prob >= self.config.classifier_trigger_threshold
            except Exception as e:
                logger.debug("Classifier trigger check failed: %s", e)

        return (
            peak_vel_trigger
            or avg_vel_trigger
            or ratio_drop_trigger
            or angular_vel_trigger
            or classifier_trigger
        )

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
            features_snapshot=None,
        )
        self.transitions.append(trans)
        logger.debug(
            "Track V3 (%s, %d) transition %s -> %s at %.3fs: %s",
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
        """Process latest track observation history and update state machine v3."""
        if not history:
            return self.state, None

        feats: TemporalFeaturesV3 | MultiScaleTemporalFeatures
        if self.config.use_multiscale_windowing:
            feats = extract_multiscale_temporal_features(
                history,
                MultiScaleWindowConfig(
                    short_window_sec=self.config.short_window_sec,
                    medium_window_sec=self.config.medium_window_sec,
                    long_window_sec=self.config.long_window_sec,
                ),
            )
        else:
            feats = extract_temporal_features_v3(history, window_seconds=self.config.feature_window_sec)

        current_time = float(history[-1].timestamp)
        self.last_observation_timestamp = current_time
        emitted_event: FallEvent | None = None

        if self.state == FallState.NORMAL:
            if self._is_rapid_descent(feats):
                self.candidate_timestamp = current_time
                self.candidate_features = feats
                self.down_frame_count = 1 if self._is_low_posture(feats) else 0
                peak_v = (
                    feats.max_scale_normalized_peak_velocity
                    if isinstance(feats, MultiScaleTemporalFeatures)
                    else feats.scale_normalized_peak_velocity
                )
                ang_v = (
                    feats.max_angular_velocity_deg_per_sec
                    if isinstance(feats, MultiScaleTemporalFeatures)
                    else feats.angular_velocity_deg_per_sec
                )
                self._transition_to(
                    FallState.DESCENT_CANDIDATE,
                    current_time,
                    f"Rapid descent v3: peak_vel={peak_v:.2f}h/s, "
                    f"angular_vel={ang_v:.2f}",
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

                # Track gap awareness
                req_frames = self.config.min_down_confirming_frames
                if feats.track_gap_count > 0:
                    req_frames += 2  # Require more confirming frames if gap

                if self.down_frame_count >= req_frames:
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
                    classifier_prob: float | None = None
                    if self.config.use_learned_classifier and self.classifier is not None:
                        try:
                            classifier_prob = self.classifier.predict_probability(
                                feats.feature_vector
                            )
                        except Exception as e:
                            logger.debug("Classifier prediction failed in down confirmation: %s", e)

                    # ADL false alert suppression & calibrated veto gate:
                    if self.config.enable_adl_suppression:
                        supp_res = self.adl_suppressor.evaluate_suppression(
                            features=feats,
                            history=history,
                            classifier_probability=classifier_prob,
                        )
                        if supp_res.suppressed:
                            self.candidate_timestamp = None
                            self.candidate_features = None
                            self.down_start_timestamp = None
                            self.down_frame_count = 0
                            self._transition_to(
                                FallState.NORMAL,
                                current_time,
                                f"Down confirmation suppressed ({supp_res.reason.value}): {supp_res.explanation}",
                                feats,
                            )
                            return self.state, emitted_event
                    elif (
                        classifier_prob is not None
                        and classifier_prob < self.config.classifier_veto_threshold
                    ):
                        self.candidate_timestamp = None
                        self.candidate_features = None
                        self.down_start_timestamp = None
                        self.down_frame_count = 0
                        self._transition_to(
                            FallState.NORMAL,
                            current_time,
                            f"Down confirmation vetoed: classifier probability "
                            f"{classifier_prob:.3f} < {self.config.classifier_veto_threshold:.3f}",
                            feats,
                        )
                        return self.state, emitted_event

                    effective_prob = classifier_prob if classifier_prob is not None else 0.85
                    confidence_val = min(
                        1.0,
                        max(
                            0.5,
                            0.5 * effective_prob
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
                        unstable_track_penalty=0.1 if feats.track_gap_count > 0 else 0.0,
                        average_pose_confidence=round(
                            feats.current_geometry.keypoint_confidence_mean, 4
                        ),
                        key_contributing_features={
                            "scale_norm_peak_vel": round(feats.scale_normalized_peak_velocity, 3),
                            "aspect_ratio": round(feats.current_geometry.aspect_ratio, 3),
                            "torso_angle": round(feats.current_geometry.torso_angle_deg, 1),
                            "classifier_prob": round(effective_prob, 3),
                        },
                        config_version="3.0.0",
                    )

                    event = FallEvent(
                        camera_id=self.camera_id,
                        track_id=self.track_id,
                        confirmed_timestamp=current_time,
                        candidate_timestamp=self.candidate_timestamp or current_time,
                        down_start_timestamp=down_time,
                        features=None,
                        confidence=breakdown.composite_confidence,
                        reason="Down posture sustained after rapid descent (v3 engine)",
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
                        f"Fall confirmed v3 (conf={breakdown.composite_confidence:.2f}): "
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


class FallStateMachineManagerV3:
    """Manages per-person FallStateMachineV3 instances across multiple camera tracks."""

    def __init__(
        self,
        config: FallStateMachineConfigV3 | None = None,
        confidence_config: FallConfidenceConfig | None = None,
        cooldown_manager: IncidentCooldownManager | None = None,
        classifier: TemporalClassifierV3Base | Any | None = None,
    ) -> None:
        self.config = config or FallStateMachineConfigV3()
        self.confidence_config = confidence_config or FallConfidenceConfig()
        self.cooldown_manager = cooldown_manager
        self.classifier = classifier if classifier is not None else _get_default_v3_classifier()
        self._machines: dict[tuple[str, int], TrackFallStateMachineV3] = {}
        self._stitcher: TrackStitcher | None = (
            TrackStitcher(
                TrackStitchConfig(
                    max_gap_frames=self.config.stitch_max_gap_frames,
                    spatial_threshold=self.config.stitch_spatial_threshold,
                    keypoint_similarity_threshold=self.config.stitch_keypoint_similarity_threshold,
                )
            )
            if self.config.enable_track_stitching
            else None
        )

    def get_machine(self, camera_id: str, track_id: int) -> TrackFallStateMachineV3:
        """Get or create state machine for (camera_id, track_id)."""
        key = (camera_id, track_id)
        if key not in self._machines:
            self._machines[key] = TrackFallStateMachineV3(
                camera_id=camera_id,
                track_id=track_id,
                config=self.config,
                confidence_config=self.confidence_config,
                cooldown_manager=self.cooldown_manager,
                classifier=self.classifier,
            )
        return self._machines[key]

    def resolve_canonical_track_id(
        self, track_id: int, history: Sequence[TrackObservation]
    ) -> int:
        """Resolve canonical track ID applying track stitching if enabled."""
        if self._stitcher is None:
            return track_id

        canonical_id = self._stitcher.get_canonical_track_id(track_id)
        if canonical_id == track_id and len(history) >= 2:
            stitched = self._stitcher.try_stitch(track_id, list(history))
            if stitched is not None:
                canonical_id = stitched
        return canonical_id

    def update_track(
        self,
        camera_id: str,
        track_id: int,
        history: Sequence[TrackObservation],
    ) -> tuple[FallState, FallEvent | None]:
        """Update state machine for a track with optional track stitching."""
        canonical_id = self.resolve_canonical_track_id(track_id, history)
        machine = self.get_machine(camera_id, canonical_id)
        return machine.update(history)

    def get_state(self, camera_id: str, track_id: int) -> FallState:
        """Get state for track, or NORMAL if not found."""
        if self._stitcher is not None:
            track_id = self._stitcher.get_canonical_track_id(track_id)
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

    @property
    def stitcher(self) -> TrackStitcher | None:
        """Access the underlying TrackStitcher instance."""
        return self._stitcher
