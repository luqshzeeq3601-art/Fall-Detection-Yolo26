# ruff: noqa: N803, N806, E501
"""Phase 11.7 V4 Threshold Calibration Engine.

Computes Precision-Recall, ROC, and F-beta curves across the full threshold spectrum.
Determines optimal operational threshold triplets:
- veto_threshold: Probability below which candidate falls are suppressed
- trigger_threshold: Probability threshold to enter CANDIDATE_DESCENT
- confirmation_threshold: Probability threshold to confirm CONFIRMED_FALL
Generates config/fall_detection_v4.yaml with calibrated values.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sklearn.metrics import auc


@dataclass(frozen=True)
class CalibrationPoint:
    threshold: float
    tpr: float
    fpr: float
    precision: float
    recall: float
    specificity: float
    f1: float
    f2: float
    tp: int
    fp: int
    tn: int
    fn: int


@dataclass(frozen=True)
class ThresholdTriplet:
    veto_threshold: float
    trigger_threshold: float
    confirmation_threshold: float
    sensitivity: float
    specificity: float
    f1_score: float
    f2_score: float
    notes: str = ""

    def validate(self) -> None:
        """Validate mathematical and operational ordering constraints."""
        if not (0.0 < self.veto_threshold <= self.trigger_threshold <= self.confirmation_threshold < 1.0):
            raise ValueError(
                f"Invalid threshold ordering: veto ({self.veto_threshold}) <= "
                f"trigger ({self.trigger_threshold}) <= confirmation ({self.confirmation_threshold}) violated."
            )


@dataclass
class OperatingCurveSummary:
    points: list[CalibrationPoint]
    auc_roc: float
    auc_pr: float
    best_f1_threshold: float
    best_f2_threshold: float
    high_sensitivity_threshold: float
    high_specificity_threshold: float


class ThresholdCalibratorEngineV4:
    """Multi-metric threshold calibration engine on empirical probabilities."""

    @staticmethod
    def compute_curves(
        y_true: np.ndarray,
        y_probs: np.ndarray,
        n_points: int = 101,
    ) -> OperatingCurveSummary:
        """Compute full spectrum of ROC, PR, and F-beta points."""
        thresholds = np.linspace(0.01, 0.99, n_points)
        points: list[CalibrationPoint] = []

        total_pos = int(np.sum(y_true == 1))
        total_neg = int(np.sum(y_true == 0))

        if total_pos == 0 or total_neg == 0:
            raise ValueError("Dataset must contain both positive and negative samples.")

        for t in thresholds:
            preds = (y_probs >= t).astype(int)

            tp = int(np.sum((preds == 1) & (y_true == 1)))
            fp = int(np.sum((preds == 1) & (y_true == 0)))
            tn = int(np.sum((preds == 0) & (y_true == 0)))
            fn = int(np.sum((preds == 0) & (y_true == 1)))

            tpr = tp / total_pos if total_pos > 0 else 0.0
            recall = tpr
            fpr = fp / total_neg if total_neg > 0 else 0.0
            specificity = tn / total_neg if total_neg > 0 else 0.0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0

            f1 = (
                2.0 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            f2 = (
                5.0 * precision * recall / (4.0 * precision + recall)
                if (4.0 * precision + recall) > 0
                else 0.0
            )

            points.append(
                CalibrationPoint(
                    threshold=float(t),
                    tpr=float(tpr),
                    fpr=float(fpr),
                    precision=float(precision),
                    recall=float(recall),
                    specificity=float(specificity),
                    f1=float(f1),
                    f2=float(f2),
                    tp=tp,
                    fp=fp,
                    tn=tn,
                    fn=fn,
                )
            )

        # Compute AUC metrics
        # For ROC: sort by FPR ascending
        sorted_by_fpr = sorted(points, key=lambda p: p.fpr)
        fpr_arr = np.array([p.fpr for p in sorted_by_fpr])
        tpr_arr = np.array([p.tpr for p in sorted_by_fpr])
        auc_roc = float(auc(fpr_arr, tpr_arr))

        # For PR: sort by Recall ascending
        sorted_by_rec = sorted(points, key=lambda p: p.recall)
        rec_arr = np.array([p.recall for p in sorted_by_rec])
        prec_arr = np.array([p.precision for p in sorted_by_rec])
        auc_pr = float(auc(rec_arr, prec_arr))

        # Find key thresholds
        best_f1_pt = max(points, key=lambda p: p.f1)
        best_f2_pt = max(points, key=lambda p: p.f2)

        # High sensitivity threshold (Sensitivity >= 0.90 with highest precision)
        sens_candidates = [p for p in points if p.recall >= 0.90]
        high_sens_pt = max(sens_candidates, key=lambda p: p.precision) if sens_candidates else best_f2_pt

        # High specificity threshold (Specificity >= 0.95 with highest recall)
        spec_candidates = [p for p in points if p.specificity >= 0.95]
        high_spec_pt = max(spec_candidates, key=lambda p: p.recall) if spec_candidates else best_f1_pt

        return OperatingCurveSummary(
            points=points,
            auc_roc=auc_roc,
            auc_pr=auc_pr,
            best_f1_threshold=best_f1_pt.threshold,
            best_f2_threshold=best_f2_pt.threshold,
            high_sensitivity_threshold=high_sens_pt.threshold,
            high_specificity_threshold=high_spec_pt.threshold,
        )

    @classmethod
    def find_optimal_triplet(
        cls,
        y_true: np.ndarray,
        y_probs: np.ndarray,
        target_sensitivity: float = 0.90,
        min_specificity: float = 0.90,
    ) -> ThresholdTriplet:
        """Find optimal veto, trigger, and confirmation thresholds."""
        summary = cls.compute_curves(y_true, y_probs)

        # 1. Trigger threshold: high recall to trigger descent candidate
        trigger_candidates = [p for p in summary.points if p.recall >= target_sensitivity]
        if not trigger_candidates:
            trigger_pt = max(summary.points, key=lambda p: p.f2)
        else:
            # Pick highest threshold meeting sensitivity to minimize spurious triggers
            trigger_pt = max(trigger_candidates, key=lambda p: p.threshold)

        trigger_t = round(trigger_pt.threshold, 2)

        # 2. Confirmation threshold: higher threshold required for confirmed fall
        confirm_candidates = [p for p in summary.points if p.threshold >= trigger_t]
        if confirm_candidates:
            # Pick threshold maximizing F1 or precision while keeping recall >= 0.85
            confirm_pt = max(
                confirm_candidates,
                key=lambda p: (p.recall >= 0.85, p.precision, p.f1),
            )
            confirm_t = round(max(trigger_t, confirm_pt.threshold), 2)
        else:
            confirm_t = min(0.95, round(trigger_t + 0.05, 2))

        # 3. Veto threshold: lower threshold below which descent is discarded as spurious
        # Must be <= trigger_t and achieve near-perfect specificity on negative frames
        veto_candidates = [p for p in summary.points if p.threshold <= trigger_t and p.recall >= 0.95]
        if veto_candidates:
            veto_pt = min(veto_candidates, key=lambda p: abs(p.threshold - (trigger_t - 0.10)))
            veto_t = round(min(trigger_t, max(0.05, veto_pt.threshold)), 2)
        else:
            veto_t = round(max(0.05, trigger_t - 0.10), 2)

        # Ensure strict ordering: veto <= trigger <= confirmation
        if veto_t > trigger_t:
            veto_t = round(max(0.05, trigger_t - 0.05), 2)
        if confirm_t < trigger_t:
            confirm_t = round(min(0.95, trigger_t + 0.05), 2)

        triplet = ThresholdTriplet(
            veto_threshold=veto_t,
            trigger_threshold=trigger_t,
            confirmation_threshold=confirm_t,
            sensitivity=trigger_pt.recall,
            specificity=trigger_pt.specificity,
            f1_score=trigger_pt.f1,
            f2_score=trigger_pt.f2,
            notes=f"Calibrated on dev split (N={len(y_true)}). Target sensitivity: {target_sensitivity}.",
        )
        triplet.validate()
        return triplet

    @staticmethod
    def generate_v4_yaml_config(
        triplet: ThresholdTriplet,
        base_yaml_path: Path,
        output_yaml_path: Path,
    ) -> Path:
        """Read base config and output calibrated config/fall_detection_v4.yaml."""
        if not base_yaml_path.is_file():
            raise FileNotFoundError(f"Base config not found: {base_yaml_path}")

        data: dict[str, Any] = yaml.safe_load(base_yaml_path.read_text(encoding="utf-8"))

        # Update learned_classifier section
        if "learned_classifier" not in data:
            data["learned_classifier"] = {}

        data["learned_classifier"]["enabled"] = True
        data["learned_classifier"]["model_type"] = "gru"
        data["learned_classifier"]["model_weights_path"] = "models/temporal_fall_classifier_v4.json"
        data["learned_classifier"]["feature_dim"] = 24
        data["learned_classifier"]["trigger_threshold"] = triplet.trigger_threshold
        data["learned_classifier"]["confirmation_threshold"] = triplet.confirmation_threshold
        data["learned_classifier"]["veto_threshold"] = triplet.veto_threshold

        # Update models section
        if "models" not in data:
            data["models"] = {}
        data["models"]["temporal_classifier"] = "models/temporal_fall_classifier_v4.json"
        data["models"]["config_version"] = "4.0.0"

        if "fall_engine_v3" in data:
            data["fall_engine_v4"] = data.pop("fall_engine_v3")
            data["fall_engine_v4"]["feature_schema_version"] = "4.0.0"

        output_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        output_yaml_path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
        return output_yaml_path
