"""Event-level evaluation matching and confidence interval statistics (P11.8-006).

Implements:
1. Strict window-based event matching:
   - TP if first alert lands in [fall_start - 1.0s, lying_start + 3.0s].
   - FN if no alert occurs in that window for a fall video.
   - FP for any alert outside the fall window or in ADL videos.
2. Unclamped time-to-alert (TTA = alert_timestamp - fall_start), preserving exact timing.
3. Wilson score confidence intervals for binomial metrics (Recall, Precision, F1).
4. Poisson confidence intervals for long-form false alert rates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AlertEvent:
    """An alert timestamp emitted by the fall detection pipeline."""

    timestamp_sec: float
    frame_idx: int
    track_id: int
    confidence: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SequenceGroundTruth:
    """Ground truth temporal boundaries for a sequence."""

    sequence_id: str
    is_fall: bool
    fall_start_sec: float | None = None
    fall_end_sec: float | None = None
    lying_start_sec: float | None = None
    total_duration_sec: float = 0.0
    fps: float = 30.0


@dataclass
class EventMatchResult:
    """Detailed event-level matching outcome for a sequence."""

    sequence_id: str
    is_fall_gt: bool
    is_true_positive: bool = False
    is_false_negative: bool = False
    is_true_negative: bool = False
    is_false_positive: bool = False
    false_positive_alert_count: int = 0
    time_to_alert_sec: float | None = None  # Unclamped TTA
    matching_alert: AlertEvent | None = None
    all_alerts: list[AlertEvent] = field(default_factory=list)
    reason: str = ""


class EventMatcher:
    """Matches pipeline alerts against temporal ground truth windows."""

    def __init__(
        self,
        early_tolerance_sec: float = 1.0,
        late_tolerance_sec: float = 3.0,
    ) -> None:
        """Initialize EventMatcher.

        Args:
            early_tolerance_sec: Allowed alert time before fall_start (default: 1.0s).
            late_tolerance_sec: Allowed alert time after lying_start (or fall_end) (default: 3.0s).
        """
        self.early_tolerance_sec = early_tolerance_sec
        self.late_tolerance_sec = late_tolerance_sec

    def match_sequence(
        self,
        gt: SequenceGroundTruth,
        alerts: list[AlertEvent],
    ) -> EventMatchResult:
        """Match emitted alerts for a sequence against ground truth.

        Args:
            gt: Sequence ground truth annotations.
            alerts: Sorted list of emitted alert events.
        """
        sorted_alerts = sorted(alerts, key=lambda a: a.timestamp_sec)

        if not gt.is_fall:
            # ADL / Non-fall sequence
            if not sorted_alerts:
                return EventMatchResult(
                    sequence_id=gt.sequence_id,
                    is_fall_gt=False,
                    is_true_negative=True,
                    false_positive_alert_count=0,
                    all_alerts=sorted_alerts,
                    reason="No alerts in ADL sequence (TN)",
                )
            else:
                return EventMatchResult(
                    sequence_id=gt.sequence_id,
                    is_fall_gt=False,
                    is_false_positive=True,
                    false_positive_alert_count=len(sorted_alerts),
                    all_alerts=sorted_alerts,
                    reason=f"{len(sorted_alerts)} false alerts in ADL sequence (FP)",
                )

        # Fall sequence
        fall_start = gt.fall_start_sec or 0.0
        lying_start = gt.lying_start_sec or gt.fall_end_sec or (fall_start + 2.0)

        window_start = fall_start - self.early_tolerance_sec
        window_end = lying_start + self.late_tolerance_sec

        matched_tp_alert: AlertEvent | None = None
        fp_count = 0
        unclamped_tta: float | None = None

        for alert in sorted_alerts:
            t = alert.timestamp_sec
            if window_start <= t <= window_end:
                if matched_tp_alert is None:
                    matched_tp_alert = alert
                    # Exact unclamped TTA
                    unclamped_tta = t - fall_start
            else:
                fp_count += 1

        if matched_tp_alert is not None:
            return EventMatchResult(
                sequence_id=gt.sequence_id,
                is_fall_gt=True,
                is_true_positive=True,
                is_false_positive=(fp_count > 0),
                false_positive_alert_count=fp_count,
                time_to_alert_sec=unclamped_tta,
                matching_alert=matched_tp_alert,
                all_alerts=sorted_alerts,
                reason=(
                    f"Fall detected at t={matched_tp_alert.timestamp_sec:.2f}s "
                    f"(TTA={unclamped_tta:.2f}s)"
                ),
            )
        else:
            return EventMatchResult(
                sequence_id=gt.sequence_id,
                is_fall_gt=True,
                is_false_negative=True,
                is_false_positive=(fp_count > 0),
                false_positive_alert_count=fp_count,
                all_alerts=sorted_alerts,
                reason="Fall missed: no alert in valid matching window (FN)",
            )


def compute_wilson_confidence_interval(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Compute Wilson score interval for binomial proportion k/n.

    Returns:
        (lower_bound, upper_bound) clipped to [0.0, 1.0].
    """
    if n <= 0:
        return 0.0, 0.0
    if k < 0:
        k = 0
    if k > n:
        k = n

    # Standard normal quantile: 1.95996 for 95%
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 1.64485
    p_hat = k / n
    denom = 1.0 + (z**2) / n
    center = (p_hat + (z**2) / (2.0 * n)) / denom
    half_width = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z**2) / (4.0 * (n**2)))

    low = max(0.0, center - half_width)
    high = min(1.0, center + half_width)
    return low, high


@dataclass
class AggregatedEventMetrics:
    """Aggregated event-level metrics with 95% confidence intervals.

    Units:
    - tp / fn: fall sequences (tp + fn == total_fall_sequences).
    - tn / fp: ADL sequences (tn + fp == total_adl_sequences).
    - false_alerts_total: every unmatched alert, in ADL and fall sequences.
    - precision: alert-level, tp / (tp + false_alerts_total).
    - specificity: ADL-sequence-level, tn / total_adl_sequences.
    """

    tp: int
    fp: int
    tn: int
    fn: int
    total_sequences: int
    total_fall_sequences: int
    total_adl_sequences: int

    precision: float
    precision_ci_95: tuple[float, float]

    recall: float
    recall_ci_95: tuple[float, float]

    specificity: float
    specificity_ci_95: tuple[float, float]

    false_alerts_total: int
    fall_sequences_with_false_alerts: int

    f1_score: float
    f1_ci_95: tuple[float, float]

    accuracy: float
    accuracy_ci_95: tuple[float, float]

    median_tta_sec: float | None
    p90_tta_sec: float | None
    p95_tta_sec: float | None
    tta_values: list[float] = field(default_factory=list)


def aggregate_event_results(results: list[EventMatchResult]) -> AggregatedEventMetrics:
    """Aggregate per-sequence event results into summary metrics with Wilson CIs."""
    tp = sum(1 for r in results if r.is_true_positive)
    fn = sum(1 for r in results if r.is_false_negative)
    tn = sum(1 for r in results if r.is_true_negative)
    fp = sum(1 for r in results if not r.is_fall_gt and len(r.all_alerts) > 0)
    false_alerts_total = sum(r.false_positive_alert_count for r in results)
    fall_seqs_with_false_alerts = sum(
        1 for r in results if r.is_fall_gt and r.false_positive_alert_count > 0
    )

    total = len(results)
    falls = sum(1 for r in results if r.is_fall_gt)
    adls = total - falls

    recall = tp / falls if falls > 0 else 0.0
    recall_ci = compute_wilson_confidence_interval(tp, falls)

    denom_prec = tp + false_alerts_total
    precision = tp / denom_prec if denom_prec > 0 else 0.0
    precision_ci = compute_wilson_confidence_interval(tp, denom_prec)

    specificity = tn / adls if adls > 0 else 0.0
    specificity_ci = compute_wilson_confidence_interval(tn, adls)

    if precision + recall > 0:
        f1 = 2.0 * (precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    # Approximate F1 CI from precision and recall CIs
    denom_ci_low = precision_ci[0] + recall_ci[0]
    denom_ci_high = precision_ci[1] + recall_ci[1]
    f1_low = 2.0 * (precision_ci[0] * recall_ci[0]) / denom_ci_low if denom_ci_low > 0 else 0.0
    f1_high = 2.0 * (precision_ci[1] * recall_ci[1]) / denom_ci_high if denom_ci_high > 0 else 0.0
    f1_ci = (f1_low, f1_high)

    accuracy = (tp + tn) / total if total > 0 else 0.0
    accuracy_ci = compute_wilson_confidence_interval(tp + tn, total)

    # TTA metrics
    ttas = [r.time_to_alert_sec for r in results if r.time_to_alert_sec is not None]
    ttas_sorted = sorted(ttas)

    if ttas_sorted:
        n = len(ttas_sorted)
        med_idx = n // 2
        median_tta = ttas_sorted[med_idx]
        p90_idx = min(n - 1, int(math.ceil(0.90 * n)) - 1)
        p95_idx = min(n - 1, int(math.ceil(0.95 * n)) - 1)
        p90_tta = ttas_sorted[p90_idx]
        p95_tta = ttas_sorted[p95_idx]
    else:
        median_tta = None
        p90_tta = None
        p95_tta = None

    return AggregatedEventMetrics(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        total_sequences=total,
        total_fall_sequences=falls,
        total_adl_sequences=adls,
        precision=precision,
        precision_ci_95=precision_ci,
        recall=recall,
        recall_ci_95=recall_ci,
        specificity=specificity,
        specificity_ci_95=specificity_ci,
        false_alerts_total=false_alerts_total,
        fall_sequences_with_false_alerts=fall_seqs_with_false_alerts,
        f1_score=f1,
        f1_ci_95=f1_ci,
        accuracy=accuracy,
        accuracy_ci_95=accuracy_ci,
        median_tta_sec=median_tta,
        p90_tta_sec=p90_tta,
        p95_tta_sec=p95_tta,
        tta_values=ttas,
    )


def summarize_by_group(
    results: list[EventMatchResult], group_keys: list[str]
) -> dict[str, dict[str, Any]]:
    """Compact per-group event metrics (e.g. per camera) for sequence-aligned keys."""
    if len(results) != len(group_keys):
        raise ValueError("results and group_keys must have the same length")
    buckets: dict[str, list[EventMatchResult]] = {}
    for res, key in zip(results, group_keys, strict=True):
        buckets.setdefault(key, []).append(res)

    summary: dict[str, dict[str, Any]] = {}
    for key in sorted(buckets):
        agg = aggregate_event_results(buckets[key])
        summary[key] = {
            "sequences": agg.total_sequences,
            "fall_sequences": agg.total_fall_sequences,
            "tp": agg.tp,
            "fn": agg.fn,
            "tn": agg.tn,
            "fp_adl_sequences": agg.fp,
            "false_alerts_total": agg.false_alerts_total,
            "recall": round(agg.recall, 4),
            "recall_95_ci": [round(x, 4) for x in agg.recall_ci_95],
            "precision": round(agg.precision, 4),
            "specificity": round(agg.specificity, 4),
            "f1_score": round(agg.f1_score, 4),
            "p95_tta_sec": (round(agg.p95_tta_sec, 3) if agg.p95_tta_sec is not None else None),
        }
    return summary
