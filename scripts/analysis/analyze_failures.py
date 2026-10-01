"""Rule-based Failure Mode Analyzer (P11.8-007).

Derives failure categories, physical root causes, and engineering mitigations
algorithmically from evaluation ledgers and sequence observations by deterministic rules,
eliminating hardcoded error mappings.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("analyze_failures")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class FailureCategory(str, Enum):
    """Standardized 4-tier taxonomy of vision-based fall detection failures."""

    CAT_A_OCCLUSION_TRUNCATION = "Category A: Occlusion & Boundary Truncation"
    CAT_B_KINETIC_AMBIGUITY = "Category B: Kinetic Ambiguity & Low-Posture Overlap"
    CAT_C_SLOW_PROGRESSIVE_SLUMP = "Category C: Low-Velocity & Progressive Slumps"
    CAT_D_KEYPOINT_JITTER_CONTRAST = "Category D: Keypoint Jitter & Lighting / Resolution"


@dataclass
class FailureDiagnosticRecord:
    """Diagnosed failure case derived by rule."""

    sequence_id: str
    error_type: str  # "FP" or "FN"
    ground_truth: str
    prediction: str
    category: FailureCategory
    rule_applied: str
    root_cause: str
    contributing_factors: list[str]
    engineering_mitigation: str
    metrics: dict[str, Any]


class FailureTaxonomyAnalyzer:
    """Classifies misclassifications into failure taxonomy categories using deterministic rules."""

    def classify_failure(
        self,
        sequence_id: str,
        error_type: str,
        is_fall_gt: bool,
        seq_metadata: dict[str, Any] | None = None,
    ) -> FailureDiagnosticRecord:
        """Classify a single error by quantitative feature inspection."""
        meta = seq_metadata or {}
        activity = str(meta.get("activity", "unknown")).lower()
        keypoint_avail = float(meta.get("usable_pose_rate", 1.0))
        id_switches = int(meta.get("id_switches", 0))
        touches_boundary = bool(meta.get("touches_boundary", False))
        peak_velocity = float(meta.get("peak_velocity", 0.0))
        descent_duration = float(meta.get("descent_duration_sec", 1.0))
        jitter_score = float(meta.get("keypoint_jitter", 0.0))

        gt_str = "Fall" if is_fall_gt else "ADL"
        pred_str = "Normal" if is_fall_gt else "Fall_Alert"

        # Rule 1: Category A - Occlusion / Boundary / ID switch
        if touches_boundary or id_switches > 0 or keypoint_avail < 0.70:
            category = FailureCategory.CAT_A_OCCLUSION_TRUNCATION
            rule = "Rule_A_Boundary_Occlusion"
            root_cause = "Person occluded by furniture/foreground or truncated at image boundary."
            factors = [
                f"Usable pose rate: {keypoint_avail * 100:.1f}%",
                f"ID switches: {id_switches}",
                f"Boundary contact: {touches_boundary}",
            ]
            mitigation = "Apply boundary-aware aspect ratio normalization and track stitching across occlusion gaps."

        # Rule 2: Category D - Keypoint Jitter / Low Contrast
        elif jitter_score > 0.15 or keypoint_avail < 0.85:
            category = FailureCategory.CAT_D_KEYPOINT_JITTER_CONTRAST
            rule = "Rule_D_Jitter_Contrast"
            root_cause = (
                "Keypoint instability / motion blur caused intermittent feature disruption."
            )
            factors = [
                f"Jitter score: {jitter_score:.3f}",
                f"Usable pose rate: {keypoint_avail * 100:.1f}%",
            ]
            mitigation = "Apply temporal Savitzky-Golay keypoint filtering and confidence masking."

        # Rule 3: Category C - Slow progressive slump / Controlled fainting (FN)
        elif is_fall_gt and (peak_velocity < 0.35 or descent_duration > 1.8):
            category = FailureCategory.CAT_C_SLOW_PROGRESSIVE_SLUMP
            rule = "Rule_C_Slow_Slump"
            root_cause = (
                "Descent velocity fell below dynamic velocity trigger; gradual slide to ground."
            )
            factors = [
                f"Peak descent velocity: {peak_velocity:.3f} h/s",
                f"Descent duration: {descent_duration:.2f} s",
            ]
            mitigation = (
                "Incorporate multi-scale long-window floor proximity and multi-layer temporal CNN."
            )

        # Rule 4: Category B - Kinetic ambiguity in ADL (FP) or fast sitting/lying
        else:
            category = FailureCategory.CAT_B_KINETIC_AMBIGUITY
            rule = "Rule_B_Kinetic_Ambiguity"
            root_cause = f"Normal movement ({activity}) exhibited velocity/posture profile mimicking fall descent."
            factors = [
                f"Activity type: {activity}",
                f"Peak descent velocity: {peak_velocity:.3f} h/s",
            ]
            mitigation = (
                "Enhance ADL suppression classifier and require sustained post-impact stillness."
            )

        return FailureDiagnosticRecord(
            sequence_id=sequence_id,
            error_type=error_type,
            ground_truth=gt_str,
            prediction=pred_str,
            category=category,
            rule_applied=rule,
            root_cause=root_cause,
            contributing_factors=factors,
            engineering_mitigation=mitigation,
            metrics={
                "usable_pose_rate": keypoint_avail,
                "id_switches": id_switches,
                "touches_boundary": touches_boundary,
                "peak_velocity": peak_velocity,
                "descent_duration_sec": descent_duration,
                "keypoint_jitter": jitter_score,
            },
        )

    def analyze_evaluation_ledger(self, evaluation_json_path: Path | str) -> dict[str, Any]:
        """Parse evaluation JSON and classify all FP and FN sequences by rule."""
        p = Path(evaluation_json_path)
        if not p.is_file():
            raise FileNotFoundError(f"Evaluation ledger not found: {evaluation_json_path}")

        data = json.loads(p.read_text(encoding="utf-8"))
        seq_details = data.get("sequence_details", {})

        diagnostics: list[FailureDiagnosticRecord] = []

        for seq_id, detail in seq_details.items():
            is_fall_gt = bool(detail.get("is_fall", False))
            is_tp = bool(detail.get("is_true_positive", False))
            is_fp = bool(detail.get("is_false_positive", False))
            is_fn = bool(detail.get("is_false_negative", False))

            if is_fn:
                rec = self.classify_failure(seq_id, "FN", is_fall_gt=True, seq_metadata=detail)
                diagnostics.append(rec)
            elif is_fp or (not is_fall_gt and detail.get("alert_count", 0) > 0):
                rec = self.classify_failure(seq_id, "FP", is_fall_gt=False, seq_metadata=detail)
                diagnostics.append(rec)

        # Category distribution
        counts_by_cat: dict[str, int] = {cat.value: 0 for cat in FailureCategory}
        for d in diagnostics:
            counts_by_cat[d.category.value] += 1

        return {
            "source_evaluation": str(p.name),
            "total_failures_diagnosed": len(diagnostics),
            "category_distribution": counts_by_cat,
            "failure_records": [asdict(d) for d in diagnostics],
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Derive failure taxonomy by rule from evaluation ledger."
    )
    parser.add_argument(
        "--eval-json",
        type=Path,
        default=ROOT / "docs" / "reports" / "P11.7-016-v4-test-evaluation.json",
        help="Path to evaluation JSON ledger",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "docs" / "reports" / "failure-taxonomy-rule-analysis.json",
        help="Path for output diagnostic ledger",
    )
    args = parser.parse_args()

    analyzer = FailureTaxonomyAnalyzer()
    report = analyzer.analyze_evaluation_ledger(args.eval_json)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info(
        "Successfully analyzed %d failure cases. Saved to %s",
        report["total_failures_diagnosed"],
        args.out_json,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
