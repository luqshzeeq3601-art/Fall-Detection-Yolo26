"""Phase 11.8 V6.1 Real-Time Fall Detection Pipeline.

Same model stack as the frozen V5 pipeline (``pipeline_v5.py`` is hash-locked in
``models/v5_freeze_manifest.json`` and must not change). V6.1 adds:
1. Kinetic precedence (no alert from a fallen-only posture).
2. Geometric floor check trusted only for full-body detections that are not cut
   off by the image border (bottom-edge contact optionally allowed: a person lying
   on the floor near the camera often touches the bottom edge).
3. ADL suppressor evaluated even when the geometric floor check fires, optionally
   ignored during/just after a kinetic peak (it otherwise vetoes genuine falls as
   "controlled sitting/bending").
4. One alert per lying episode (latched until the person is upright again).

Processing is split into two stages so calibration can replay the exact
deployed decision logic without re-running the model:
- ``compute_signals``: threshold-independent per-frame signals (model + geometry + suppressor).
- ``DecisionStageV61.step``: threshold/flag-dependent post-processing that emits alerts.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from eldercare.fall_engine.features.multiscale import (
    MultiScaleWindowConfig,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
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

LOG = logging.getLogger("pipeline_v6_1")

LEG_KEYPOINT_INDICES = (11, 12, 13, 14, 15, 16)


def default_post_processor_config_v61() -> PostProcessorConfigV5:
    """V6.1 post-processor defaults (thresholds are overwritten by calibration)."""
    return PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.30,
        require_falling_motion=True,
        suppress_until_upright=True,
    )


@dataclass
class PipelineConfigV61:
    """V6.1 pipeline configuration."""

    history_window_seconds: float = 2.5
    target_fps: float = 15.0
    post_processor: PostProcessorConfigV5 = field(
        default_factory=default_post_processor_config_v61
    )
    adl_suppression: ADLSuppressionConfig = field(default_factory=ADLSuppressionConfig)
    multiscale_windows: MultiScaleWindowConfig = field(
        default_factory=MultiScaleWindowConfig
    )
    max_track_history_length: int = 60
    min_leg_keypoint_confidence: float = 0.35
    edge_margin_px: float = 5.0
    # Fix B: when False, touching the bottom image edge does not disable the floor check.
    edge_check_bottom: bool = True
    bypass_suppressor_on_floor: bool = False
    # Fix A: ignore the heuristic ADL suppressor while p_falling >= trigger and for
    # ``kinetic_peak_hold_sec`` afterwards.
    suppress_only_without_kinetic_peak: bool = False
    kinetic_peak_hold_sec: float = 2.0


@dataclass(frozen=True)
class FrameSignalsV61:
    """Threshold-independent per-frame signals for one tracked observation."""

    camera_id: str
    track_id: int
    timestamp: float
    has_history: bool
    p_falling: float = 0.0
    p_fallen: float = 0.0
    geometric_floor: bool = (
        False  # aspect/torso-angle floor posture, before trust gating
    )
    has_full_body: bool = False
    touches_bottom_edge: bool = False
    touches_other_edge: bool = False
    is_upright: bool = False
    heuristic_suppressed: bool = False
    features: Any | None = None


def is_floor_posture(sig: FrameSignalsV61, config: PipelineConfigV61) -> bool:
    """Apply the configured trust gating to the raw geometric floor signal."""
    if not (sig.geometric_floor and sig.has_full_body):
        return False
    if sig.touches_other_edge:
        return False
    return not (config.edge_check_bottom and sig.touches_bottom_edge)


class DecisionStageV61:
    """Threshold-dependent post-processing shared by live inference and calibration replay."""

    def __init__(self, config: PipelineConfigV61) -> None:
        self.config = config
        self._post_processors: dict[tuple[str, int], PostProcessorV5] = {}
        self._camera_fall_candidates: dict[str, float] = {}
        self._last_kinetic_peak: dict[tuple[str, int], float] = {}

    def reset(self) -> None:
        self._post_processors.clear()
        self._camera_fall_candidates.clear()
        self._last_kinetic_peak.clear()

    def get_post_processor(self, camera_id: str, track_id: int) -> PostProcessorV5:
        key = (camera_id, track_id)
        if key not in self._post_processors:
            self._post_processors[key] = PostProcessorV5(
                config=self.config.post_processor,
                camera_id=camera_id,
                track_id=track_id,
            )
        return self._post_processors[key]

    def _suppressor_applies(self, sig: FrameSignalsV61, is_floor: bool) -> bool:
        if not sig.heuristic_suppressed:
            return False
        if is_floor and self.config.bypass_suppressor_on_floor:
            return False
        if self.config.suppress_only_without_kinetic_peak:
            last_peak = self._last_kinetic_peak.get((sig.camera_id, sig.track_id))
            if (
                last_peak is not None
                and sig.timestamp - last_peak <= self.config.kinetic_peak_hold_sec
            ):
                return False
        return True

    def step(self, sig: FrameSignalsV61) -> tuple[FallState, FallEvent | None]:
        pp_cfg = self.config.post_processor
        post_proc = self.get_post_processor(sig.camera_id, sig.track_id)

        # Camera-level candidate handover for tracking fragmentation
        if (
            post_proc.fall_candidate_time is None
            and sig.camera_id in self._camera_fall_candidates
        ):
            cam_t = self._camera_fall_candidates[sig.camera_id]
            if (sig.timestamp - cam_t) <= pp_cfg.transition_max_window_sec:
                post_proc.fall_candidate_time = cam_t

        if not sig.has_history:
            return FallState.NORMAL, None

        is_floor = is_floor_posture(sig, self.config)
        is_low_posture = bool(
            is_floor or sig.p_fallen >= pp_cfg.down_confirmation_threshold
        )

        if sig.p_falling >= pp_cfg.fall_trigger_threshold:
            self._camera_fall_candidates[sig.camera_id] = sig.timestamp
            self._last_kinetic_peak[(sig.camera_id, sig.track_id)] = sig.timestamp

        candidate_active = (post_proc.fall_candidate_time is not None) or (
            sig.p_falling >= pp_cfg.fall_trigger_threshold
        )
        if candidate_active and self._suppressor_applies(sig, is_floor):
            post_proc.reset_candidate()
            return FallState.NORMAL, None

        alert_triggered = post_proc.update(
            timestamp=sig.timestamp,
            p_falling=sig.p_falling,
            p_fallen=sig.p_fallen,
            is_low_posture=is_low_posture,
            is_upright=sig.is_upright,
        )

        if alert_triggered:
            event = FallEvent(
                camera_id=sig.camera_id,
                track_id=sig.track_id,
                confirmed_timestamp=sig.timestamp,
                candidate_timestamp=sig.timestamp,
                down_start_timestamp=sig.timestamp,
                features=sig.features,  # type: ignore[arg-type]
                confidence=float(sig.p_falling + sig.p_fallen),
                reason="Sustained low posture after fall transition",
            )
            return FallState.FALL_CONFIRMED, event

        if post_proc.fall_candidate_time is not None:
            if is_low_posture:
                return FallState.DOWN_CONFIRMING, None
            return FallState.DESCENT_CANDIDATE, None
        if sig.p_falling >= pp_cfg.fall_trigger_threshold:
            return FallState.DESCENT_CANDIDATE, None
        return FallState.NORMAL, None


def observations_from_cached_sequence(
    seq: Any,
    camera_id: str,
    max_center_jump_frac: float | None = None,
    relock_after_sec: float = 1.0,
    stats: dict[str, int] | None = None,
) -> list[TrackObservation]:
    """Convert a cached keypoint sequence into per-frame observations (first person only).

    The cache stores one person per frame without identity tracking. When
    ``max_center_jump_frac`` is set, a frame whose bbox centre jumps more than that
    fraction of the image diagonal from the last kept frame is treated as an
    identity switch and dropped, unless more than ``relock_after_sec`` has passed
    since the last kept frame (then the new detection is accepted).
    ``stats`` (if given) receives ``kept`` and ``dropped_identity_jumps`` counts.
    """
    observations: list[TrackObservation] = []
    last_center: tuple[float, float] | None = None
    last_t: float | None = None
    dropped = 0
    for f in seq.frames:
        if not f.persons:
            continue
        p = f.persons[0]
        x1, y1, x2, y2 = p.bbox_xyxy
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        if (
            max_center_jump_frac is not None
            and last_center is not None
            and last_t is not None
            and f.timestamp - last_t <= relock_after_sec
        ):
            diag = math.hypot(f.image_width or 640, f.image_height or 480)
            jump = math.hypot(center[0] - last_center[0], center[1] - last_center[1])
            if jump > max_center_jump_frac * diag:
                dropped += 1
                continue
        last_center, last_t = center, f.timestamp
        observations.append(
            TrackObservation(
                camera_id=camera_id,
                track_id=p.track_id or 1,
                timestamp=f.timestamp,
                bbox_xyxy=p.bbox_xyxy,
                detection_confidence=p.detection_confidence,
                keypoints=p.keypoints,
                image_width=f.image_width,
                image_height=f.image_height,
            )
        )
    if stats is not None:
        stats["kept"] = stats.get("kept", 0) + len(observations)
        stats["dropped_identity_jumps"] = (
            stats.get("dropped_identity_jumps", 0) + dropped
        )
    return observations


def replay_signals(
    signals: Iterable[FrameSignalsV61],
    config: PipelineConfigV61,
) -> list[float]:
    """Run the V6.1 decision stage over precomputed signals; return alert timestamps."""
    stage = DecisionStageV61(config)
    alerts: list[float] = []
    for sig in signals:
        _, event = stage.step(sig)
        if event is not None:
            alerts.append(sig.timestamp)
    return alerts


class FallEnginePipelineV61:
    """V6.1 real-time fall detection pipeline (M2 skeleton classifier + post-processing)."""

    def __init__(
        self,
        skeleton_classifier: TemporalSkeletonClassifierV5,
        config: PipelineConfigV61 | None = None,
    ) -> None:
        self.config = config or PipelineConfigV61()
        self.skeleton_classifier = skeleton_classifier
        self.adl_suppressor = ADLFalseAlertSuppressor(self.config.adl_suppression)
        self.decision = DecisionStageV61(self.config)
        self._track_histories: dict[int, list[TrackObservation]] = defaultdict(list)

    def reset(self) -> None:
        """Reset all per-sequence state."""
        self._track_histories.clear()
        self.decision.reset()

    def _get_post_processor(self, camera_id: str, track_id: int) -> PostProcessorV5:
        return self.decision.get_post_processor(camera_id, track_id)

    def _body_visibility(self, obs: TrackObservation) -> tuple[bool, bool, bool]:
        """Return (has_full_body, touches_bottom_edge, touches_other_edge)."""
        kpts = obs.keypoints
        leg_confs = [
            float(kpts[i].confidence)
            for i in LEG_KEYPOINT_INDICES
            if i < len(kpts) and kpts[i].present and kpts[i].confidence is not None
        ]
        mean_leg_conf = float(np.mean(leg_confs)) if leg_confs else 0.0
        has_full_body = mean_leg_conf >= self.config.min_leg_keypoint_confidence

        margin = self.config.edge_margin_px
        if margin <= 0.0:
            return has_full_body, False, False
        x1, y1, x2, y2 = obs.bbox_xyxy
        img_w = float(obs.image_width or 640)
        img_h = float(obs.image_height or 480)
        touches_bottom = y2 >= (img_h - margin)
        touches_other = x1 <= margin or y1 <= margin or x2 >= (img_w - margin)
        return has_full_body, bool(touches_bottom), bool(touches_other)

    def compute_signals(
        self, obs: TrackObservation, keep_features: bool = True
    ) -> FrameSignalsV61:
        """Update track history and compute threshold-independent signals for ``obs``."""
        tid = obs.track_id
        hist = self._track_histories[tid]
        hist.append(obs)

        cutoff = obs.timestamp - self.config.history_window_seconds
        while len(hist) > 1 and hist[0].timestamp < cutoff:
            hist.pop(0)
        if len(hist) > self.config.max_track_history_length:
            hist.pop(0)

        if len(hist) < 3:
            return FrameSignalsV61(
                camera_id=obs.camera_id,
                track_id=tid,
                timestamp=obs.timestamp,
                has_history=False,
            )

        multi_feats = extract_multiscale_temporal_features(
            hist, self.config.multiscale_windows
        )
        _, p_falling, p_fallen = self.skeleton_classifier.predict_probabilities(hist)
        p_falling = float(p_falling)
        p_fallen = float(p_fallen)

        geom = multi_feats.current_geometry
        geometric_floor = bool(
            geom.aspect_ratio <= 1.05
            or (geom.aspect_ratio <= 1.30 and geom.torso_angle_deg <= 45.0)
        )
        has_full_body, touches_bottom, touches_other = self._body_visibility(obs)
        is_upright = bool(
            geom.aspect_ratio >= 1.35
            and geom.torso_angle_deg >= 65.0
            and p_falling < 0.20
            and p_fallen < 0.20
        )

        # The suppressor is stateless, so evaluating it on every frame is equivalent to
        # evaluating it only while a candidate is active. Classifier veto is ignored, as in V5.
        supp_res = self.adl_suppressor.evaluate_suppression(
            multi_feats, hist, classifier_probability=p_falling + p_fallen
        )
        heuristic_suppressed = bool(
            supp_res.suppressed and supp_res.reason.value != "CLASSIFIER_VETO"
        )

        return FrameSignalsV61(
            camera_id=obs.camera_id,
            track_id=tid,
            timestamp=obs.timestamp,
            has_history=True,
            p_falling=p_falling,
            p_fallen=p_fallen,
            geometric_floor=geometric_floor,
            has_full_body=has_full_body,
            touches_bottom_edge=touches_bottom,
            touches_other_edge=touches_other,
            is_upright=is_upright,
            heuristic_suppressed=heuristic_suppressed,
            features=(
                getattr(multi_feats, "medium_features", None) if keep_features else None
            ),
        )

    def process_observation(
        self, obs: TrackObservation
    ) -> tuple[FallState, FallEvent | None]:
        """Process one tracked observation. Returns (FallState, FallEvent | None)."""
        return self.decision.step(self.compute_signals(obs))
