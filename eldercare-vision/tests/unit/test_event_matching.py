"""Unit tests for EventMatcher and confidence interval statistics (P11.8-006).

Verifies:
1. Strict windowed TP matching: [fall_start - 1.0s, lying_start + 3.0s].
2. Early and late alerts classified as false positives.
3. ADL sequences with/without alerts classified as FP/TN.
4. Unclamped time-to-alert calculation.
5. Wilson score confidence interval correctness.
"""

from __future__ import annotations

import pytest

from eldercare.fall_engine.evaluation.event_matching import (
    AlertEvent,
    EventMatcher,
    SequenceGroundTruth,
    aggregate_event_results,
    compute_wilson_confidence_interval,
)


@pytest.fixture
def matcher() -> EventMatcher:
    return EventMatcher(early_tolerance_sec=1.0, late_tolerance_sec=3.0)


def test_valid_alert_within_window_is_tp(matcher: EventMatcher) -> None:
    """Alert occurring inside [fall_start - 1s, lying_start + 3s] must be TP with unclamped TTA."""
    gt = SequenceGroundTruth(
        sequence_id="fall_01",
        is_fall=True,
        fall_start_sec=5.0,
        fall_end_sec=6.5,
        lying_start_sec=7.0,
    )
    alerts = [AlertEvent(timestamp_sec=5.8, frame_idx=174, track_id=1)]

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_positive is True
    assert res.is_false_negative is False
    assert res.time_to_alert_sec == pytest.approx(0.8, abs=1e-4)


def test_unclamped_tta_before_fall_start(matcher: EventMatcher) -> None:
    """Alert before fall_start within early tolerance has negative unclamped TTA."""
    gt = SequenceGroundTruth(
        sequence_id="fall_02",
        is_fall=True,
        fall_start_sec=10.0,
        fall_end_sec=11.0,
        lying_start_sec=11.5,
    )
    alerts = [AlertEvent(timestamp_sec=9.5, frame_idx=285, track_id=1)]

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_positive is True
    assert res.time_to_alert_sec == pytest.approx(-0.5, abs=1e-4)


def test_early_alert_outside_tolerance_is_fp(matcher: EventMatcher) -> None:
    """Alert occurring earlier than fall_start - 1.0s is FP and results in FN for the fall."""
    gt = SequenceGroundTruth(
        sequence_id="fall_03",
        is_fall=True,
        fall_start_sec=10.0,
        fall_end_sec=11.0,
        lying_start_sec=11.5,
    )
    # Alert at t=3.0s is way before window_start=9.0s
    alerts = [AlertEvent(timestamp_sec=3.0, frame_idx=90, track_id=1)]

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_positive is False
    assert res.is_false_negative is True
    assert res.is_false_positive is True
    assert res.false_positive_alert_count == 1


def test_late_alert_after_lying_window_is_fp(matcher: EventMatcher) -> None:
    """Alert occurring after lying_start + 3.0s is FP and fall is missed (FN)."""
    gt = SequenceGroundTruth(
        sequence_id="fall_04",
        is_fall=True,
        fall_start_sec=4.0,
        fall_end_sec=5.0,
        lying_start_sec=5.5,
    )
    # Window ends at 5.5 + 3.0 = 8.5s. Alert at 10.0s is too late.
    alerts = [AlertEvent(timestamp_sec=10.0, frame_idx=300, track_id=1)]

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_positive is False
    assert res.is_false_negative is True
    assert res.is_false_positive is True


def test_adl_without_alerts_is_tn(matcher: EventMatcher) -> None:
    """ADL sequence with no alerts is True Negative."""
    gt = SequenceGroundTruth(
        sequence_id="adl_01",
        is_fall=False,
    )
    alerts: list[AlertEvent] = []

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_negative is True
    assert res.is_false_positive is False
    assert res.false_positive_alert_count == 0


def test_adl_with_alert_is_fp(matcher: EventMatcher) -> None:
    """ADL sequence emitting an alert is False Positive."""
    gt = SequenceGroundTruth(
        sequence_id="adl_02",
        is_fall=False,
    )
    alerts = [AlertEvent(timestamp_sec=2.5, frame_idx=75, track_id=1)]

    res = matcher.match_sequence(gt, alerts)
    assert res.is_true_negative is False
    assert res.is_false_positive is True
    assert res.false_positive_alert_count == 1


def test_wilson_confidence_interval_bounds() -> None:
    """Verify Wilson interval properties: 0 <= low <= p <= high <= 1."""
    low, high = compute_wilson_confidence_interval(k=95, n=100, confidence=0.95)
    assert 0.88 <= low <= 0.95
    assert 0.95 <= high <= 0.99
    assert low < high

    # Edge cases
    assert compute_wilson_confidence_interval(0, 0) == (0.0, 0.0)
    low_0, high_0 = compute_wilson_confidence_interval(0, 50)
    assert low_0 == 0.0 and high_0 > 0.0


def test_aggregated_event_metrics(matcher: EventMatcher) -> None:
    """Verify full aggregation across multiple fall and ADL sequences."""
    # 2 Fall sequences (1 TP, 1 FN)
    gt_fall1 = SequenceGroundTruth("fall_1", is_fall=True, fall_start_sec=2.0, lying_start_sec=3.0)
    gt_fall2 = SequenceGroundTruth("fall_2", is_fall=True, fall_start_sec=2.0, lying_start_sec=3.0)

    # 2 ADL sequences (1 TN, 1 FP)
    gt_adl1 = SequenceGroundTruth("adl_1", is_fall=False)
    gt_adl2 = SequenceGroundTruth("adl_2", is_fall=False)

    r1 = matcher.match_sequence(gt_fall1, [AlertEvent(2.5, 75, 1)])  # TP
    r2 = matcher.match_sequence(gt_fall2, [])                        # FN
    r3 = matcher.match_sequence(gt_adl1, [])                         # TN
    r4 = matcher.match_sequence(gt_adl2, [AlertEvent(1.0, 30, 1)])   # FP

    metrics = aggregate_event_results([r1, r2, r3, r4])
    assert metrics.tp == 1
    assert metrics.fn == 1
    assert metrics.tn == 1
    assert metrics.fp == 1
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.f1_score == pytest.approx(0.5)
    assert metrics.accuracy == pytest.approx(0.5)
    assert metrics.median_tta_sec == pytest.approx(0.5)
