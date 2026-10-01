"""Phase 11.8 V5 Model Ablation Ladder & Classifier Implementations (P11.8-017..022).

Defines the 4 model candidates on the ablation ladder:
- M0: V4 Baseline Retrained (GRU / Logistic on 24-dim features)
- M1: HistGradientBoosting on multi-scale hand features (72-dim)
- M2: Temporal CNN-GRU on 15 Hz normalized keypoint tensors (72-dim x 30 frames)
- M3: Feature-Fused Ensemble (M1 + M2 soft voting)

Includes PostProcessorV5 enforcing falling -> fallen transition logic with cooldown.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from eldercare.fall_engine.confidence.cooldown import IncidentCooldownManager
from eldercare.fall_engine.features.multiscale import (
    MultiScaleTemporalFeatures,
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.vision.tracking.observation import TrackObservation

LOG = logging.getLogger("classifier_v5")


@dataclass(frozen=True)
class PostProcessorConfigV5:
    """Post-processor temporal progression thresholds."""

    fall_trigger_threshold: float = 0.35
    down_confirmation_threshold: float = 0.35
    min_down_sustain_seconds: float = 0.15
    transition_max_window_sec: float = 2.00
    cooldown_seconds: float = 5.00
    require_falling_motion: bool = False
    suppress_until_upright: bool = False


class PostProcessorV5:
    """Enforces falling -> fallen transition within <= 2s and sustained fallen state."""

    def __init__(
        self,
        config: PostProcessorConfigV5 | None = None,
        camera_id: str = "cam_0",
        track_id: int = 1,
    ) -> None:
        from eldercare.fall_engine.confidence.cooldown import CooldownConfig

        self.config = config or PostProcessorConfigV5()
        self.camera_id = camera_id
        self.track_id = track_id
        self.cooldown_mgr = IncidentCooldownManager(
            config=CooldownConfig(incident_cooldown_sec=self.config.cooldown_seconds)
        )
        self.fall_candidate_time: float | None = None
        self.down_start_time: float | None = None
        self.is_in_alerted_episode: bool = False
        self.max_p_falling_in_candidate: float = 0.0

    def reset(self) -> None:
        """Reset temporal state."""
        self.fall_candidate_time = None
        self.down_start_time = None
        self.is_in_alerted_episode = False
        self.max_p_falling_in_candidate = 0.0

    def reset_candidate(self) -> None:
        """Clear the pending candidate but keep the post-alert episode latch."""
        self.fall_candidate_time = None
        self.down_start_time = None
        self.max_p_falling_in_candidate = 0.0

    def update(
        self,
        timestamp: float,
        p_falling: float,
        p_fallen: float,
        is_low_posture: bool,
        is_upright: bool = False,
    ) -> bool:
        """Process frame probabilities and determine if fall event is confirmed.

        Returns True if a new confirmed fall alert should be emitted.
        """
        if self.config.suppress_until_upright and self.is_in_alerted_episode:
            if (
                is_upright
                and not is_low_posture
                and p_fallen < self.config.down_confirmation_threshold
            ):
                self.is_in_alerted_episode = False
            else:
                return False

        if self.cooldown_mgr.is_in_cooldown(self.camera_id, self.track_id, timestamp):
            return False

        # 1. Check for kinetic falling candidate or direct high-confidence fallen candidate
        if p_falling >= self.config.fall_trigger_threshold:
            if self.fall_candidate_time is None:
                self.fall_candidate_time = timestamp
                self.max_p_falling_in_candidate = p_falling
            else:
                self.max_p_falling_in_candidate = max(self.max_p_falling_in_candidate, p_falling)
        elif (
            not self.config.require_falling_motion
            and p_fallen >= self.config.down_confirmation_threshold
            and self.fall_candidate_time is None
        ):
            self.fall_candidate_time = timestamp
            self.max_p_falling_in_candidate = 0.0

        # 2. Check for transition to fallen within <= 2.0s window
        if self.fall_candidate_time is not None:
            elapsed_since_fall = timestamp - self.fall_candidate_time
            if elapsed_since_fall > self.config.transition_max_window_sec:
                self.fall_candidate_time = None
                self.down_start_time = None
                self.max_p_falling_in_candidate = 0.0
            elif (p_fallen >= self.config.down_confirmation_threshold) or is_low_posture:
                if (
                    self.config.require_falling_motion
                    and self.max_p_falling_in_candidate < self.config.fall_trigger_threshold
                ):
                    self.fall_candidate_time = None
                    self.down_start_time = None
                    self.max_p_falling_in_candidate = 0.0
                    return False

                if self.down_start_time is None:
                    self.down_start_time = timestamp
                if (timestamp - self.down_start_time) >= self.config.min_down_sustain_seconds or (
                    p_falling >= 0.80 and is_low_posture
                ):
                    # Confirmed sustained fall!
                    self.cooldown_mgr.record_incident(self.camera_id, self.track_id, timestamp)
                    self.fall_candidate_time = None
                    self.down_start_time = None
                    self.max_p_falling_in_candidate = 0.0
                    if self.config.suppress_until_upright:
                        self.is_in_alerted_episode = True
                    return True

        return False


class ClassifierV5M1_HistGBDT:
    """M1 Model: HistGradientBoosting on multi-scale hand-crafted features."""

    def __init__(
        self,
        model: HistGradientBoostingClassifier | None = None,
        training_sequence_ids: list[str] | None = None,
        manifest_sha256: str = "",
        trained_at: str = "",
    ) -> None:
        self.model = model or HistGradientBoostingClassifier(
            max_iter=60,
            learning_rate=0.08,
            max_leaf_nodes=31,
            early_stopping=True,
            class_weight="balanced",
            random_state=42,
        )
        self.training_sequence_ids = list(training_sequence_ids or [])
        self.manifest_sha256 = manifest_sha256
        self.trained_at = trained_at

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        training_sequence_ids: Sequence[str] | None = None,
        manifest_sha256: str = "",
    ) -> None:
        """Train classifier on feature matrix X (N, D) and labels y (N,)."""
        self.model.fit(X, y)
        if training_sequence_ids is not None:
            self.training_sequence_ids = list(training_sequence_ids)
        if manifest_sha256:
            self.manifest_sha256 = manifest_sha256

    def predict_probability(self, feature_vector: Sequence[float] | np.ndarray) -> float:
        """Predict probability of fall (class 1)."""
        x_arr = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)
        probs = self.model.predict_proba(x_arr)[0]
        return float(probs[1]) if len(probs) > 1 else float(probs[0])

    def save(self, path: str | Path) -> None:
        """Serialize model and metadata to disk."""
        dest = Path(path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "metadata": {
                "training_sequence_ids": self.training_sequence_ids,
                "manifest_sha256": self.manifest_sha256,
                "trained_at": self.trained_at,
            },
        }
        joblib.dump(payload, dest)

    @classmethod
    def load(cls, path: str | Path) -> ClassifierV5M1_HistGBDT:
        """Load serialized model from disk with metadata support."""
        dest = Path(path).resolve()
        loaded = joblib.load(dest)
        if isinstance(loaded, dict) and "model" in loaded:
            meta = loaded.get("metadata", {})
            return cls(
                model=loaded["model"],
                training_sequence_ids=meta.get("training_sequence_ids", []),
                manifest_sha256=meta.get("manifest_sha256", ""),
                trained_at=meta.get("trained_at", ""),
            )
        return cls(model=loaded)


class ClassifierV5M3_Fused:
    """M3 Model: Feature-Fused Ensemble (M1 HistGBDT + M2 Temporal Skeleton GRU)."""

    def __init__(
        self,
        m1_model: ClassifierV5M1_HistGBDT,
        m2_model: TemporalSkeletonClassifierV5,
        weight_m1: float = 0.4,
        weight_m2: float = 0.6,
    ) -> None:
        self.m1 = m1_model
        self.m2 = m2_model
        self.weight_m1 = weight_m1
        self.weight_m2 = weight_m2

    def predict_fall_confidence(
        self,
        history: Sequence[TrackObservation | Any],
        multiscale_features: MultiScaleTemporalFeatures | None = None,
    ) -> float:
        """Fuse predictions from M1 and M2."""
        if multiscale_features is None:
            multiscale_features = extract_multiscale_temporal_features(history)

        feat_vec_m1 = multiscale_features.fused_feature_vector
        prob_m1 = self.m1.predict_probability(feat_vec_m1)
        prob_m2 = self.m2.predict_fall_confidence(history)

        return float(self.weight_m1 * prob_m1 + self.weight_m2 * prob_m2)
