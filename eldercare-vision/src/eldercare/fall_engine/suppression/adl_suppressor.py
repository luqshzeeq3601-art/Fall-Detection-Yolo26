# ruff: noqa: E501
"""Complex ADL False-Alert Suppressor (Phase 11.7 P11.7-012).

Provides heuristic and learned secondary suppression gates for challenging ADLs:
- Controlled bending (picking up objects, tying shoes)
- Controlled sitting (sofas, chairs, wheelchair transfers)
- Intentional reclining / lying down (bed, couch)
- Calibrated classifier veto filtering (< tau_veto = 0.55)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from eldercare.fall_engine.features.features_v3 import (
    PoseGeometryFeaturesV3,
    TemporalFeaturesV3,
)
from eldercare.fall_engine.features.multiscale import MultiScaleTemporalFeatures
from eldercare.vision.tracking.observation import TrackObservation

logger = logging.getLogger(__name__)


class SuppressionReason(str, Enum):
    """Categorical reasons for suppressing a candidate fall alert."""

    NONE = "NONE"
    CLASSIFIER_VETO = "CLASSIFIER_VETO"
    CONTROLLED_BENDING = "CONTROLLED_BENDING"
    CONTROLLED_SITTING = "CONTROLLED_SITTING"
    INTENTIONAL_RECLINING = "INTENTIONAL_RECLINING"
    ELEVATED_HIP_SURFACE = "ELEVATED_HIP_SURFACE"


@dataclass(frozen=True)
class ADLSuppressionConfig:
    """Configurable parameters for ADL false alert suppression."""

    enabled: bool = True
    classifier_veto_threshold: float = 0.55  # Calibrated tau_veto
    bending_max_kinetic_accel: float = 0.25  # Controlled bending lacks kinetic impact
    bending_ankle_stability_thresh: float = 0.15  # Feet remain planted during bending
    sitting_min_hip_elevation_ratio: float = 0.25  # Hip remains elevated on chair/sofa
    reclining_max_peak_velocity: float = 0.55  # Intentional lying is controlled and slow
    reclining_min_stability: float = 0.05      # Stable post-transition posture


@dataclass(frozen=True)
class SuppressionResult:
    """Evaluation output from ADL False Alert Suppressor."""

    suppressed: bool
    reason: SuppressionReason
    confidence: float
    explanation: str
    metrics: dict[str, float] = field(default_factory=dict)


class ADLFalseAlertSuppressor:
    """Heuristic and calibrated secondary suppressor for complex ADLs."""

    def __init__(self, config: ADLSuppressionConfig | None = None) -> None:
        self.config = config or ADLSuppressionConfig()

    def evaluate_suppression(
        self,
        features: TemporalFeaturesV3 | MultiScaleTemporalFeatures,
        history: Sequence[TrackObservation],
        classifier_probability: float | None = None,
    ) -> SuppressionResult:
        """Evaluate whether a candidate fall event should be suppressed.

        Args:
            features: Single or multi-scale temporal features of the track.
            history: Sequence of track observations.
            classifier_probability: Predicted fall probability from learned model.

        Returns:
            SuppressionResult indicating if suppressed, reason, and explanation.
        """
        if not self.config.enabled:
            return SuppressionResult(
                suppressed=False,
                reason=SuppressionReason.NONE,
                confidence=0.0,
                explanation="ADL suppression is disabled.",
            )

        # 1. Calibrated Classifier Veto Gate
        if classifier_probability is not None:
            if classifier_probability < self.config.classifier_veto_threshold:
                return SuppressionResult(
                    suppressed=True,
                    reason=SuppressionReason.CLASSIFIER_VETO,
                    confidence=1.0 - classifier_probability,
                    explanation=(
                        f"Classifier probability ({classifier_probability:.4f}) below "
                        f"veto threshold ({self.config.classifier_veto_threshold:.4f})."
                    ),
                    metrics={"classifier_prob": classifier_probability},
                )

        if not history:
            return SuppressionResult(
                suppressed=False,
                reason=SuppressionReason.NONE,
                confidence=0.0,
                explanation="No history available for suppression evaluation.",
            )

        # Extract kinematic features
        if isinstance(features, MultiScaleTemporalFeatures):
            peak_vel = features.max_scale_normalized_peak_velocity
            cent_acc = features.max_centroid_acceleration
            norm_disp = features.max_normalized_vertical_displacement
            ref_h = features.reference_height
            curr_geom = features.current_geometry
            stability = features.post_descent_motion_stability
        else:
            peak_vel = features.scale_normalized_peak_velocity
            cent_acc = features.centroid_acceleration
            norm_disp = features.normalized_vertical_displacement
            ref_h = features.reference_height
            curr_geom = features.current_geometry
            stability = features.post_descent_motion_stability

        # 2. Controlled Bending Filter (e.g. picking up object from floor, tying shoes)
        # Signatures:
        # - Feet / ankles remain stationary/planted on the floor.
        # - Centroid acceleration is low / smooth (no impact shock).
        # - Torso tilts forward, but head/shoulders do not collide with ground.
        ankle_y_movement = self._compute_ankle_vertical_movement(history, ref_h)
        if (
            cent_acc < self.config.bending_max_kinetic_accel
            and ankle_y_movement < self.config.bending_ankle_stability_thresh
            and curr_geom.torso_angle_deg < 50.0
            and peak_vel < 0.65
        ):
            return SuppressionResult(
                suppressed=True,
                reason=SuppressionReason.CONTROLLED_BENDING,
                confidence=0.85,
                explanation=(
                    f"Controlled bending detected: planted feet (ankle_disp={ankle_y_movement:.2f}h), "
                    f"smooth acceleration (acc={cent_acc:.2f}h/s^2), peak_vel={peak_vel:.2f}h/s."
                ),
                metrics={
                    "ankle_y_movement": ankle_y_movement,
                    "centroid_acceleration": cent_acc,
                    "peak_velocity": peak_vel,
                },
            )

        # 3. Controlled Sitting Filter (e.g. sitting down on chair, sofa, bed)
        # Signatures:
        # - Hip center remains elevated above floor/foot plane (seated height ratio >= 0.25h).
        # - Vertical velocity decelerates smoothly before coming to rest.
        # - Torso remains relatively upright (angle >= 45 deg) or reclined comfortably.
        hip_elevation = self._compute_hip_elevation_ratio(curr_geom, history, ref_h)
        if (
            hip_elevation >= self.config.sitting_min_hip_elevation_ratio
            and curr_geom.torso_angle_deg >= 40.0
            and cent_acc < 0.35
            and peak_vel < 0.70
        ):
            return SuppressionResult(
                suppressed=True,
                reason=SuppressionReason.CONTROLLED_SITTING,
                confidence=0.88,
                explanation=(
                    f"Controlled sitting detected: elevated hip (elevation={hip_elevation:.2f}h), "
                    f"upright torso ({curr_geom.torso_angle_deg:.1f} deg), smooth descent."
                ),
                metrics={
                    "hip_elevation": hip_elevation,
                    "torso_angle_deg": curr_geom.torso_angle_deg,
                    "peak_velocity": peak_vel,
                },
            )

        # 4. Intentional Reclining / Lying Down on Bed Filter
        # Signatures:
        # - Peak descent velocity is moderate (< reclining_max_peak_velocity).
        # - Post-descent stability is high (no chaotic flailing or impact rebound).
        # - Smooth gradual transition without acceleration spike.
        if (
            peak_vel < self.config.reclining_max_peak_velocity
            and cent_acc < 0.20
            and norm_disp >= 0.20
            and stability < 20.0
        ):
            return SuppressionResult(
                suppressed=True,
                reason=SuppressionReason.INTENTIONAL_RECLINING,
                confidence=0.82,
                explanation=(
                    f"Intentional reclining detected: low peak velocity ({peak_vel:.2f}h/s), "
                    f"smooth descent (acc={cent_acc:.2f}h/s^2), high stability."
                ),
                metrics={
                    "peak_velocity": peak_vel,
                    "centroid_acceleration": cent_acc,
                    "stability": stability,
                },
            )

        return SuppressionResult(
            suppressed=False,
            reason=SuppressionReason.NONE,
            confidence=0.0,
            explanation="Kinematic signature consistent with uninhibited fall trajectory.",
            metrics={"peak_velocity": peak_vel, "centroid_acceleration": cent_acc},
        )

    def _compute_ankle_vertical_movement(
        self, history: Sequence[TrackObservation], ref_h: float
    ) -> float:
        """Compute relative vertical movement of ankles over the track history."""
        if len(history) < 2 or ref_h <= 0.0:
            return 0.0

        ankle_ys = []
        for obs in history:
            y_pts = []
            if len(obs.keypoints) > 16:
                la, ra = obs.keypoints[15], obs.keypoints[16]
                if la.present and la.y is not None:
                    y_pts.append(la.y)
                if ra.present and ra.y is not None:
                    y_pts.append(ra.y)
            if y_pts:
                ankle_ys.append(sum(y_pts) / len(y_pts))

        if len(ankle_ys) < 2:
            return 0.0

        y_range = max(ankle_ys) - min(ankle_ys)
        return float(y_range / ref_h)

    def _compute_hip_elevation_ratio(
        self,
        curr_geom: PoseGeometryFeaturesV3,
        history: Sequence[TrackObservation],
        ref_h: float,
    ) -> float:
        """Compute hip elevation above lowest detected body/floor point relative to reference height."""
        if ref_h <= 0.0 or curr_geom.hip_midpoint is None:
            return 0.0

        hip_y = curr_geom.hip_midpoint[1]
        max_y = hip_y
        for obs in history[-10:]:
            for k in obs.keypoints:
                if k.present and k.y is not None:
                    max_y = max(max_y, k.y)

        elevation_px = max(0.0, max_y - hip_y)
        return float(elevation_px / ref_h)
