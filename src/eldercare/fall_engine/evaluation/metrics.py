"""Classification and timing evaluation metrics for the fall detection engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationMetrics:
    """Standard evaluation metrics for sequence-level fall classification."""

    total_sequences: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    mean_time_to_alert_sec: float | None = None


def compute_metrics(
    tp: int,
    fp: int,
    tn: int,
    fn: int,
    alert_times: Sequence[float] | None = None,
) -> EvaluationMetrics:
    """Compute precision, recall, F1, accuracy, and average time-to-alert.

    Handles zero-denominator cases safely by returning 0.0.

    Args:
        tp: True positives (falls correctly confirmed).
        fp: False positives (ADLs falsely confirmed as falls).
        tn: True negatives (ADLs correctly not confirmed).
        fn: False negatives (falls missed).
        alert_times: Optional list of time-to-alert durations (seconds) for TP events.

    Returns:
        Populated EvaluationMetrics dataclass.
    """
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0

    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = ((2.0 * precision * recall) / (precision + recall)) if (precision + recall) > 0 else 0.0

    mean_tta = None
    if alert_times and len(alert_times) > 0:
        mean_tta = sum(alert_times) / len(alert_times)

    return EvaluationMetrics(
        total_sequences=total,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        accuracy=round(accuracy, 4),
        mean_time_to_alert_sec=round(mean_tta, 4) if mean_tta is not None else None,
    )
