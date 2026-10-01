"""Lightweight learned temporal fall classifier (Phase 11.5 v2).

Provides calibrated probabilistic fall detection over 12-dimensional
scale-normalized temporal posture features with sub-millisecond execution.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eldercare.fall_engine.features.motion_v2 import TemporalFeaturesV2


@dataclass(frozen=True)
class TemporalClassifierWeights:
    """Serializable parameter weights and scaling for temporal fall classifier."""

    feature_names: tuple[str, ...]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    decision_threshold: float = 0.5


# Default calibrated weights on development split
_DEFAULT_WEIGHTS = TemporalClassifierWeights(
    feature_names=(
        "scale_norm_vel",
        "scale_norm_peak_vel",
        "norm_disp",
        "aspect_ratio",
        "aspect_rel_change",
        "torso_angle",
        "torso_angle_change",
        "h_change_ratio",
        "low_dur",
        "stability",
        "avg_conf",
        "hip_height_ratio",
    ),
    mean=(0.42, 0.85, 0.35, 1.25, -0.22, 62.0, -18.0, -0.25, 0.40, 15.0, 0.72, 0.52),
    scale=(0.35, 0.55, 0.28, 0.45, 0.30, 25.0, 22.0, 0.28, 0.45, 20.0, 0.18, 0.15),
    coefficients=(
        1.85,  # High downward velocity strongly indicates fall
        1.42,  # Peak downward velocity
        1.60,  # Large vertical displacement
        -1.75,  # Low aspect ratio indicates horizontal posture on ground
        -1.30,  # Negative relative aspect ratio drop
        -1.95,  # Low torso angle (horizontal) indicates fallen posture
        -1.10,  # Negative angle change (tilting downward)
        -1.20,  # Height reduction
        0.85,  # Sustained low posture
        -0.45,  # Motionless stability on ground
        0.50,  # High keypoint confidence
        0.65,  # Hip close to bottom of bbox
    ),
    intercept=-0.80,
    decision_threshold=0.50,
)


class LearnedTemporalFallClassifier:
    """Lightweight learned temporal fall classifier using standardized logistic scoring."""

    def __init__(self, weights: TemporalClassifierWeights | None = None) -> None:
        self.weights = weights or _DEFAULT_WEIGHTS

    @classmethod
    def load_from_json(cls, path: str | Path) -> LearnedTemporalFallClassifier:
        """Load trained weights from a JSON artifact file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        weights = TemporalClassifierWeights(
            feature_names=tuple(data["feature_names"]),
            mean=tuple(data["mean"]),
            scale=tuple(data["scale"]),
            coefficients=tuple(data["coefficients"]),
            intercept=float(data["intercept"]),
            decision_threshold=float(data.get("decision_threshold", 0.5)),
        )
        return cls(weights)

    def save_to_json(self, path: str | Path) -> None:
        """Save classifier weights to a JSON file."""
        data = {
            "schema_version": "1.0.0",
            "feature_names": list(self.weights.feature_names),
            "mean": list(self.weights.mean),
            "scale": list(self.weights.scale),
            "coefficients": list(self.weights.coefficients),
            "intercept": self.weights.intercept,
            "decision_threshold": self.weights.decision_threshold,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def predict_probability(self, features: TemporalFeaturesV2 | Sequence[float]) -> float:
        """Compute calibrated fall probability in [0, 1].

        Args:
            features: A TemporalFeaturesV2 instance or a 12-element float sequence.

        Returns:
            Calibrated fall probability in [0.0, 1.0].
        """
        if isinstance(features, TemporalFeaturesV2):
            raw_vec = features.feature_vector
        else:
            raw_vec = tuple(features)

        if len(raw_vec) != len(self.weights.coefficients):
            raise ValueError(
                f"Expected {len(self.weights.coefficients)} features, got {len(raw_vec)}"
            )

        # Standardize features: (x - mean) / scale
        score = self.weights.intercept
        for x, m, s, w in zip(
            raw_vec,
            self.weights.mean,
            self.weights.scale,
            self.weights.coefficients,
            strict=False,
        ):
            norm_x = (x - m) / max(s, 1e-6)
            score += norm_x * w

        # Sigmoid activation
        # Guard against overflow
        clamped_score = max(-30.0, min(30.0, score))
        prob = 1.0 / (1.0 + math.exp(-clamped_score))
        return prob

    def is_fall(self, features: TemporalFeaturesV2 | Sequence[float]) -> bool:
        """Determine binary fall prediction based on decision threshold."""
        prob = self.predict_probability(features)
        return prob >= self.weights.decision_threshold

    def get_feature_contributions(
        self, features: TemporalFeaturesV2 | Sequence[float]
    ) -> dict[str, Any]:
        """Provide explainable feature contribution breakdown."""
        if isinstance(features, TemporalFeaturesV2):
            raw_vec = features.feature_vector
        else:
            raw_vec = tuple(features)

        contributions: dict[str, float] = {}
        for name, x, m, s, w in zip(
            self.weights.feature_names,
            raw_vec,
            self.weights.mean,
            self.weights.scale,
            self.weights.coefficients,
            strict=False,
        ):
            norm_x = (x - m) / max(s, 1e-6)
            contributions[name] = round(norm_x * w, 4)

        prob = self.predict_probability(raw_vec)
        return {
            "probability": round(prob, 4),
            "intercept": self.weights.intercept,
            "contributions": contributions,
            "is_fall": prob >= self.weights.decision_threshold,
        }
