"""V4 deployment evaluation metrics and integrity validation.

Guarantees:
1. Strict separation of short-clip ADL false positive rate from long-form false alerts/camera-hour.
2. Long-form camera hours are derived strictly from actually decoded and processed frames/seconds,
   never declared hours or truncated loops.
3. Poisson confidence intervals for long-form false alert rates.
4. Cryptographic provenance tracking (source file hashes, manifest digests, timestamp).
5. Dynamic gate checking with full auditability.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scipy.stats import chi2

    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


@dataclass
class V4EvaluationResult:
    """Evaluation result for a single recorded video sequence or continuous stream."""

    stream_id: str
    is_fall: bool = False
    is_true_positive: bool = False
    is_false_positive: bool = False
    is_false_negative: bool = False
    is_true_negative: bool = False

    # Distinction between short test clips (<30s) and continuous long-form monitoring
    is_short_clip: bool = True
    is_long_form: bool = False

    # Actual decoded duration info (NOT declared duration)
    declared_duration_seconds: float = 0.0
    actual_decoded_frames: int = 0
    fps: float = 30.0
    actual_processed_seconds: float = 0.0

    # Timing (seconds)
    time_to_alert_sec: float | None = None
    is_duplicate_alert: bool = False

    # Pose and tracking quality
    total_frames_in_fall_window: int = 0
    frames_with_usable_pose: int = 0
    expected_track_frames: int = 0
    continuous_track_frames: int = 0
    id_switches: int = 0

    # Subgroups (e.g. {"lighting": "low_light", "view": "lateral", "subject": "S01"})
    subgroup_labels: dict[str, str] = field(default_factory=dict)

    # Runtime telemetry
    processing_time_ms: float = 0.0
    e2e_latency_sec: float | None = None
    source_video_hash: str = ""

    def __post_init__(self) -> None:
        if self.actual_processed_seconds <= 0.0 and self.actual_decoded_frames > 0 and self.fps > 0:
            self.actual_processed_seconds = self.actual_decoded_frames / self.fps


@dataclass(frozen=True)
class DeploymentMetricsV4:
    """Deployment metrics adhering to Phase 11.7 metric integrity requirements."""

    # Core classification metrics
    tp: int
    fp: int
    tn: int
    fn: int
    total_sequences: int
    precision: float
    recall: float
    f1_score: float
    f2_score: float
    accuracy: float
    missed_fall_rate: float

    # Separated False Alert Metrics
    # 1. Short-clip ADL false positive rate (proportion of negative clips falsely triggered)
    short_clip_adl_fp_count: int
    short_clip_adl_total_count: int
    short_clip_adl_fp_rate: float

    # 2. Long-form continuous stream false alerts per camera hour
    long_form_false_alert_count: int
    long_form_processed_camera_hours: float
    long_form_false_alerts_per_camera_hour: float
    long_form_fa_poisson_ci: tuple[float, float]
    actual_processed_seconds: float
    actual_decoded_frames: int

    # Time to alert (seconds)
    median_tta_sec: float
    p90_tta_sec: float
    p95_tta_sec: float
    tta_samples: int

    # Operational quality
    duplicate_alert_rate: float
    usable_pose_rate: float
    track_continuity_rate: float
    id_switch_rate: float

    # Performance and latency
    throughput_fps: float
    p50_latency_ms: float
    p95_latency_ms: float
    e2e_alert_latency_sec: float
    hardware_metrics: dict[str, float]

    # Subgroup breakdowns
    subgroup_metrics: dict[str, dict[str, float]]

    # Cryptographic provenance & audit
    provenance: str  # "real_measured" | "synthetic_simulation" | "quarantined_historical"
    deployment_evidence: bool
    source_file_hashes: dict[str, str]
    input_manifest_hash: str
    evaluated_at_utc: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to JSON-serializable dictionary."""
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "total_sequences": self.total_sequences,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "f2_score": self.f2_score,
            "accuracy": self.accuracy,
            "missed_fall_rate": self.missed_fall_rate,
            "short_clip_adl_fp_count": self.short_clip_adl_fp_count,
            "short_clip_adl_total_count": self.short_clip_adl_total_count,
            "short_clip_adl_fp_rate": self.short_clip_adl_fp_rate,
            "long_form_false_alert_count": self.long_form_false_alert_count,
            "long_form_processed_camera_hours": self.long_form_processed_camera_hours,
            "long_form_false_alerts_per_camera_hour": self.long_form_false_alerts_per_camera_hour,
            "long_form_fa_poisson_ci": list(self.long_form_fa_poisson_ci),
            "actual_processed_seconds": self.actual_processed_seconds,
            "actual_decoded_frames": self.actual_decoded_frames,
            "median_tta_sec": self.median_tta_sec,
            "p90_tta_sec": self.p90_tta_sec,
            "p95_tta_sec": self.p95_tta_sec,
            "tta_samples": self.tta_samples,
            "duplicate_alert_rate": self.duplicate_alert_rate,
            "usable_pose_rate": self.usable_pose_rate,
            "track_continuity_rate": self.track_continuity_rate,
            "id_switch_rate": self.id_switch_rate,
            "throughput_fps": self.throughput_fps,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "e2e_alert_latency_sec": self.e2e_alert_latency_sec,
            "hardware_metrics": self.hardware_metrics,
            "subgroup_metrics": self.subgroup_metrics,
            "provenance": self.provenance,
            "deployment_evidence": self.deployment_evidence,
            "source_file_hashes": self.source_file_hashes,
            "input_manifest_hash": self.input_manifest_hash,
            "evaluated_at_utc": self.evaluated_at_utc,
            "notes": self.notes,
        }


def compute_poisson_confidence_interval(
    k: int, exposure_hours: float, confidence: float = 0.95
) -> tuple[float, float]:
    """Compute exact two-sided Poisson confidence interval for rate k / exposure_hours.

    Args:
        k: Observed count of events (e.g. false alerts).
        exposure_hours: Continuous camera hours actually decoded and observed.
        confidence: Confidence level (default 0.95).

    Returns:
        tuple (lower_bound_rate, upper_bound_rate) per hour.
    """
    if exposure_hours <= 0.0:
        return 0.0, 0.0

    alpha = 1.0 - confidence

    if _HAS_SCIPY:
        if k == 0:
            lower = 0.0
            upper = 0.5 * chi2.ppf(1.0 - alpha / 2.0, 2) / exposure_hours
        else:
            lower = 0.5 * chi2.ppf(alpha / 2.0, 2 * k) / exposure_hours
            upper = 0.5 * chi2.ppf(1.0 - alpha / 2.0, 2 * (k + 1)) / exposure_hours
    else:
        # Fallback approximation for Poisson CI when scipy is unavailable
        if k == 0:
            lower = 0.0
            upper = -math.log(alpha / 2.0) / exposure_hours
        else:
            z = 1.959963984540054  # 95% normal quantile
            rate = k / exposure_hours
            delta = z * math.sqrt(k) / exposure_hours
            lower = max(0.0, rate - delta)
            upper = rate + delta

    return round(lower, 4), round(upper, 4)


def _percentile(data: Sequence[float], p: float) -> float:
    """Compute percentile using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    if p >= 100.0:
        return sorted_data[-1]
    if p <= 0.0:
        return sorted_data[0]
    n = len(sorted_data)
    idx = (p / 100.0) * (n - 1)
    i = int(idx)
    if i >= n - 1:
        return sorted_data[-1]
    frac = idx - i
    return sorted_data[i] + frac * (sorted_data[i + 1] - sorted_data[i])


def compute_deployment_metrics_v4(
    results: list[V4EvaluationResult],
    provenance: str = "real_measured",
    deployment_evidence: bool = True,
    source_file_hashes: dict[str, str] | None = None,
    input_manifest_hash: str = "",
    hardware_stats: dict[str, float] | None = None,
    throughput_fps: float = 0.0,
    notes: str = "",
) -> DeploymentMetricsV4:
    """Compute strictly validated deployment metrics from real evaluation outcomes.

    Enforces that short clips and continuous long-form streams are never mixed in the
    long-form denominator, and that only processed video duration is used.
    """
    total_seqs = len(results)
    if total_seqs == 0:
        return _empty_metrics_v4(
            provenance=provenance,
            deployment_evidence=deployment_evidence,
            source_file_hashes=source_file_hashes or {},
            input_manifest_hash=input_manifest_hash,
            notes=notes,
        )

    tp = sum(1 for r in results if r.is_true_positive)
    fp = sum(1 for r in results if r.is_false_positive)
    tn = sum(1 for r in results if r.is_true_negative)
    fn = sum(1 for r in results if r.is_false_negative)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / total_seqs if total_seqs > 0 else 0.0
    f1_score = (
        (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    )
    f2_score = (
        (5.0 * precision * recall) / ((4.0 * precision) + recall)
        if (precision > 0 or recall > 0)
        else 0.0
    )
    missed_fall_rate = fn / (tp + fn) if (tp + fn) > 0 else 0.0

    # 1. Short-clip ADL False Positive Rate
    short_adl_results = [r for r in results if r.is_short_clip and not r.is_fall]
    short_clip_adl_total_count = len(short_adl_results)
    short_clip_adl_fp_count = sum(1 for r in short_adl_results if r.is_false_positive)
    short_clip_adl_fp_rate = (
        short_clip_adl_fp_count / short_clip_adl_total_count
        if short_clip_adl_total_count > 0
        else 0.0
    )

    # 2. Long-form continuous stream false alerts per camera hour
    long_form_results = [r for r in results if r.is_long_form and not r.is_fall]
    long_form_false_alert_count = sum(1 for r in long_form_results if r.is_false_positive)

    # Long-form processed hours must come from actual decoded frames or actual processed seconds
    actual_long_form_sec = sum(r.actual_processed_seconds for r in long_form_results)
    long_form_processed_camera_hours = (
        actual_long_form_sec / 3600.0 if actual_long_form_sec > 0 else 0.0
    )

    long_form_fa_rate = (
        long_form_false_alert_count / long_form_processed_camera_hours
        if long_form_processed_camera_hours > 0.0
        else 0.0
    )
    long_form_poisson_ci = compute_poisson_confidence_interval(
        k=long_form_false_alert_count,
        exposure_hours=long_form_processed_camera_hours,
        confidence=0.95,
    )

    total_actual_sec = sum(r.actual_processed_seconds for r in results)
    total_actual_frames = sum(r.actual_decoded_frames for r in results)

    # Time to alert (seconds)
    ttas = [
        r.time_to_alert_sec
        for r in results
        if r.time_to_alert_sec is not None and r.time_to_alert_sec > 0
    ]
    tta_samples = len(ttas)
    if tta_samples > 0:
        median_tta_sec = statistics.median(ttas)
        p90_tta_sec = _percentile(ttas, 90.0)
        p95_tta_sec = _percentile(ttas, 95.0)
    else:
        median_tta_sec = p90_tta_sec = p95_tta_sec = 0.0

    # Operational rates
    fall_events = tp + fn
    duplicates = sum(1 for r in results if r.is_duplicate_alert)
    duplicate_alert_rate = duplicates / fall_events if fall_events > 0 else 0.0

    total_pose_frames = sum(r.total_frames_in_fall_window for r in results)
    usable_pose_frames = sum(r.frames_with_usable_pose for r in results)
    usable_pose_rate = usable_pose_frames / total_pose_frames if total_pose_frames > 0 else 0.0

    expected_tracks = sum(r.expected_track_frames for r in results)
    continuous_tracks = sum(r.continuous_track_frames for r in results)
    track_continuity_rate = continuous_tracks / expected_tracks if expected_tracks > 0 else 0.0

    total_id_switches = sum(r.id_switches for r in results)
    id_switch_rate = total_id_switches / fall_events if fall_events > 0 else 0.0

    # Latency
    latencies = [r.processing_time_ms for r in results if r.processing_time_ms > 0]
    p50_latency = _percentile(latencies, 50.0) if latencies else 0.0
    p95_latency = _percentile(latencies, 95.0) if latencies else 0.0

    e2e_latencies = [r.e2e_latency_sec for r in results if r.e2e_latency_sec is not None]
    e2e_alert_latency = statistics.mean(e2e_latencies) if e2e_latencies else 0.0

    # Subgroups
    subgroup_metrics = _compute_subgroups(results)

    now_utc = datetime.now(timezone.utc).isoformat()

    return DeploymentMetricsV4(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        total_sequences=total_seqs,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1_score, 4),
        f2_score=round(f2_score, 4),
        accuracy=round(accuracy, 4),
        missed_fall_rate=round(missed_fall_rate, 4),
        short_clip_adl_fp_count=short_clip_adl_fp_count,
        short_clip_adl_total_count=short_clip_adl_total_count,
        short_clip_adl_fp_rate=round(short_clip_adl_fp_rate, 4),
        long_form_false_alert_count=long_form_false_alert_count,
        long_form_processed_camera_hours=round(long_form_processed_camera_hours, 4),
        long_form_false_alerts_per_camera_hour=round(long_form_fa_rate, 4),
        long_form_fa_poisson_ci=long_form_poisson_ci,
        actual_processed_seconds=round(total_actual_sec, 2),
        actual_decoded_frames=total_actual_frames,
        median_tta_sec=round(median_tta_sec, 4),
        p90_tta_sec=round(p90_tta_sec, 4),
        p95_tta_sec=round(p95_tta_sec, 4),
        tta_samples=tta_samples,
        duplicate_alert_rate=round(duplicate_alert_rate, 4),
        usable_pose_rate=round(usable_pose_rate, 4),
        track_continuity_rate=round(track_continuity_rate, 4),
        id_switch_rate=round(id_switch_rate, 4),
        throughput_fps=round(throughput_fps, 2),
        p50_latency_ms=round(p50_latency, 2),
        p95_latency_ms=round(p95_latency, 2),
        e2e_alert_latency_sec=round(e2e_alert_latency, 3),
        hardware_metrics=hardware_stats or {},
        subgroup_metrics=subgroup_metrics,
        provenance=provenance,
        deployment_evidence=deployment_evidence,
        source_file_hashes=source_file_hashes or {},
        input_manifest_hash=input_manifest_hash,
        evaluated_at_utc=now_utc,
        notes=notes,
    )


def _compute_subgroups(results: list[V4EvaluationResult]) -> dict[str, dict[str, float]]:
    """Compute recall and sample size across all subgroup tags."""
    groups: dict[str, dict[str, list[V4EvaluationResult]]] = {}
    for r in results:
        for cat, val in r.subgroup_labels.items():
            if cat not in groups:
                groups[cat] = {}
            if val not in groups[cat]:
                groups[cat][val] = []
            groups[cat][val].append(r)

    metrics: dict[str, dict[str, float]] = {}
    for cat, val_dict in groups.items():
        metrics[cat] = {}
        for val, items in val_dict.items():
            falls = [i for i in items if i.is_fall]
            if falls:
                rec_val = sum(1 for f in falls if f.is_true_positive) / len(falls)
                metrics[cat][f"{val}_recall"] = round(rec_val, 4)
                metrics[cat][f"{val}_fall_count"] = float(len(falls))
            else:
                adls = [i for i in items if not i.is_fall]
                fp_val = sum(1 for a in adls if a.is_false_positive) / len(adls) if adls else 0.0
                metrics[cat][f"{val}_fp_rate"] = round(fp_val, 4)
                metrics[cat][f"{val}_adl_count"] = float(len(adls))

    return metrics


def _empty_metrics_v4(
    provenance: str,
    deployment_evidence: bool,
    source_file_hashes: dict[str, str],
    input_manifest_hash: str,
    notes: str,
) -> DeploymentMetricsV4:
    return DeploymentMetricsV4(
        tp=0,
        fp=0,
        tn=0,
        fn=0,
        total_sequences=0,
        precision=0.0,
        recall=0.0,
        f1_score=0.0,
        f2_score=0.0,
        accuracy=0.0,
        missed_fall_rate=0.0,
        short_clip_adl_fp_count=0,
        short_clip_adl_total_count=0,
        short_clip_adl_fp_rate=0.0,
        long_form_false_alert_count=0,
        long_form_processed_camera_hours=0.0,
        long_form_false_alerts_per_camera_hour=0.0,
        long_form_fa_poisson_ci=(0.0, 0.0),
        actual_processed_seconds=0.0,
        actual_decoded_frames=0,
        median_tta_sec=0.0,
        p90_tta_sec=0.0,
        p95_tta_sec=0.0,
        tta_samples=0,
        duplicate_alert_rate=0.0,
        usable_pose_rate=0.0,
        track_continuity_rate=0.0,
        id_switch_rate=0.0,
        throughput_fps=0.0,
        p50_latency_ms=0.0,
        p95_latency_ms=0.0,
        e2e_alert_latency_sec=0.0,
        hardware_metrics={},
        subgroup_metrics={},
        provenance=provenance,
        deployment_evidence=deployment_evidence,
        source_file_hashes=source_file_hashes,
        input_manifest_hash=input_manifest_hash,
        evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )


def check_deployment_gates_v4(
    metrics: DeploymentMetricsV4, targets: dict[str, Any]
) -> dict[str, Any]:
    """Dynamically verify measured deployment metrics against defined gate targets.

    Returns:
        dict with keys: 'all_passed', 'met', 'not_met', 'summary'.
    """
    report: dict[str, Any] = {
        "all_passed": True,
        "met": [],
        "not_met": [],
    }

    def check(name: str, value: float, target: float, lower_better: bool) -> None:
        passed = value <= target if lower_better else value >= target
        entry = {
            "metric": name,
            "measured": value,
            "target": target,
            "status": "PASS" if passed else "FAIL",
            "lower_better": lower_better,
        }
        if passed:
            report["met"].append(entry)
        else:
            report["not_met"].append(entry)
            report["all_passed"] = False

    if "recall" in targets:
        check("recall", metrics.recall, targets["recall"], lower_better=False)
    if "precision" in targets:
        check("precision", metrics.precision, targets["precision"], lower_better=False)
    if "f1_score" in targets:
        check("f1_score", metrics.f1_score, targets["f1_score"], lower_better=False)
    if "f2_score" in targets:
        check("f2_score", metrics.f2_score, targets["f2_score"], lower_better=False)
    if "long_form_false_alerts_per_camera_hour" in targets:
        check(
            "long_form_false_alerts_per_camera_hour",
            metrics.long_form_false_alerts_per_camera_hour,
            targets["long_form_false_alerts_per_camera_hour"],
            lower_better=True,
        )
    if "short_clip_adl_fp_rate" in targets:
        check(
            "short_clip_adl_fp_rate",
            metrics.short_clip_adl_fp_rate,
            targets["short_clip_adl_fp_rate"],
            lower_better=True,
        )
    if "p95_tta_sec" in targets:
        check("p95_tta_sec", metrics.p95_tta_sec, targets["p95_tta_sec"], lower_better=True)
    if "usable_pose_rate" in targets:
        check(
            "usable_pose_rate",
            metrics.usable_pose_rate,
            targets["usable_pose_rate"],
            lower_better=False,
        )
    if "track_continuity_rate" in targets:
        check(
            "track_continuity_rate",
            metrics.track_continuity_rate,
            targets["track_continuity_rate"],
            lower_better=False,
        )
    if "id_switch_rate" in targets:
        check(
            "id_switch_rate", metrics.id_switch_rate, targets["id_switch_rate"], lower_better=True
        )
    if "throughput_fps" in targets:
        check(
            "throughput_fps", metrics.throughput_fps, targets["throughput_fps"], lower_better=False
        )
    if "p95_latency_ms" in targets:
        check(
            "p95_latency_ms", metrics.p95_latency_ms, targets["p95_latency_ms"], lower_better=True
        )

    report["summary"] = (
        f"{len(report['met'])}/{len(report['met']) + len(report['not_met'])} gates met"
    )
    return report


def hash_file_lf(path: Path | str) -> str:
    """Compute sha256 digest of file content normalised with LF line endings."""
    p = Path(path)
    data = p.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()
