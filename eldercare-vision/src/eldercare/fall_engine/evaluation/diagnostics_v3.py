"""V3 Root-Cause Diagnostic Audit Module (Phase 11.6).

Provides tools to systematically diagnose why the fall detection system
misclassifies sequences by categorizing errors into:
- POSE: Keypoint estimation failures
- TRACKING: ByteTrack ID switches, track gaps
- TEMPORAL: Classification threshold/feature issues
- CAMERA: Geometry/perspective/distance problems
- DATA: Annotation ambiguities, domain shift
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class PoseDiagnostic:
    """Pose quality diagnostic for a single observation."""

    timestamp: float
    present_keypoint_count: int
    mean_confidence: float
    min_confidence: float
    missing_keypoint_indices: tuple[int, ...]
    has_shoulder_pair: bool
    has_hip_pair: bool
    has_torso_vector: bool
    has_head: bool


@dataclass(frozen=True)
class TrackDiagnostic:
    """Tracking quality diagnostic for a sequence."""

    total_frames: int
    total_observations: int
    unique_track_ids: int
    id_switches: int
    max_gap_frames: int
    gap_count: int
    bbox_jump_count: int
    bbox_jump_threshold_pixels: float
    continuity_rate: float  # observations / expected_frames


@dataclass(frozen=True)
class SequenceDiagnosticReport:
    """Complete diagnostic report for one evaluation sequence."""

    sequence_id: str
    is_fall_ground_truth: bool
    is_fall_predicted: bool
    classification_correct: bool
    error_category: str | None  # POSE, TRACKING, TEMPORAL, CAMERA, DATA, or None
    error_subcategory: str | None

    # Pose diagnostics
    pose_availability_rate: float
    mean_keypoint_confidence: float
    min_phase_confidence: dict[str, float]  # pre-fall, descent, impact, down
    critical_keypoints_missing_rate: float  # hip+shoulder missing rate

    # Track diagnostics
    track_diagnostic: TrackDiagnostic | None

    # Feature diagnostics (V3)
    peak_scale_norm_velocity: float | None
    max_angular_velocity: float | None
    min_torso_angle: float | None
    min_aspect_ratio: float | None
    max_classifier_probability: float | None


@dataclass
class DiagnosticAuditSummary:
    """Aggregate diagnostic summary across all sequences."""

    total_sequences: int = 0
    total_tp: int = 0
    total_fp: int = 0
    total_tn: int = 0
    total_fn: int = 0

    error_category_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_subcategory_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    pose_availability_by_phase: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    track_id_switch_counts: list[int] = field(default_factory=list)
    track_gap_counts: list[int] = field(default_factory=list)
    track_continuity_rates: list[float] = field(default_factory=list)

    # Per-condition breakdowns
    metrics_by_camera_angle: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    )
    metrics_by_distance: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    )
    metrics_by_lighting: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    )

    def add_sequence_report(
        self,
        report: SequenceDiagnosticReport,
        camera_angle: str = "unknown",
        distance: str = "unknown",
        lighting: str = "unknown",
    ) -> None:
        """Add a sequence diagnostic to the aggregate summary."""
        self.total_sequences += 1

        if report.is_fall_ground_truth and report.is_fall_predicted:
            self.total_tp += 1
            key = "tp"
        elif not report.is_fall_ground_truth and report.is_fall_predicted:
            self.total_fp += 1
            key = "fp"
        elif not report.is_fall_ground_truth and not report.is_fall_predicted:
            self.total_tn += 1
            key = "tn"
        else:
            self.total_fn += 1
            key = "fn"

        if report.error_category:
            self.error_category_counts[report.error_category] += 1
        if report.error_subcategory:
            self.error_subcategory_counts[report.error_subcategory] += 1

        if report.track_diagnostic:
            self.track_id_switch_counts.append(report.track_diagnostic.id_switches)
            self.track_gap_counts.append(report.track_diagnostic.gap_count)
            self.track_continuity_rates.append(report.track_diagnostic.continuity_rate)

        self.metrics_by_camera_angle[camera_angle][key] += 1
        self.metrics_by_distance[distance][key] += 1
        self.metrics_by_lighting[lighting][key] += 1


def compute_pose_diagnostic(
    observation: TrackObservation,
    confidence_threshold: float = 0.3,
) -> PoseDiagnostic:
    """Compute pose quality diagnostic for a single observation."""
    kpts = observation.keypoints
    present = [
        i
        for i, k in enumerate(kpts)
        if k.present and k.x is not None and k.y is not None
    ]
    missing = [i for i in range(17) if i not in present]
    confs = [
        kpts[i].confidence for i in present if kpts[i].confidence >= 0
    ]

    mean_conf = sum(confs) / len(confs) if confs else 0.0
    min_conf = min(confs) if confs else 0.0

    # Check anatomical keypoint pairs
    has_shoulders = (5 in present) and (6 in present)
    has_hips = (11 in present) and (12 in present)
    has_torso = (has_shoulders or (5 in present) or (6 in present)) and (
        has_hips or (11 in present) or (12 in present)
    )
    has_head = 0 in present or (1 in present and 2 in present)

    return PoseDiagnostic(
        timestamp=observation.timestamp,
        present_keypoint_count=len(present),
        mean_confidence=mean_conf,
        min_confidence=min_conf,
        missing_keypoint_indices=tuple(missing),
        has_shoulder_pair=has_shoulders,
        has_hip_pair=has_hips,
        has_torso_vector=has_torso,
        has_head=has_head,
    )


def compute_track_diagnostic(
    observations: list[TrackObservation],
    expected_fps: float = 30.0,
    bbox_jump_threshold: float = 100.0,
) -> TrackDiagnostic:
    """Compute tracking quality diagnostic for a sequence of observations."""
    if not observations:
        return TrackDiagnostic(
            total_frames=0,
            total_observations=0,
            unique_track_ids=0,
            id_switches=0,
            max_gap_frames=0,
            gap_count=0,
            bbox_jump_count=0,
            bbox_jump_threshold_pixels=bbox_jump_threshold,
            continuity_rate=0.0,
        )

    track_ids = [obs.track_id for obs in observations]
    unique_ids = set(track_ids)

    # Count ID switches
    id_switches = 0
    for i in range(1, len(track_ids)):
        if track_ids[i] != track_ids[i - 1]:
            id_switches += 1

    # Count gaps (missing frames)
    timestamps = [obs.timestamp for obs in observations]
    expected_dt = 1.0 / expected_fps
    gap_count = 0
    max_gap = 0
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        gap_frames = int(dt / expected_dt) - 1
        if gap_frames > 0:
            gap_count += 1
            max_gap = max(max_gap, gap_frames)

    # Count bbox jumps
    bbox_jumps = 0
    for i in range(1, len(observations)):
        cx1 = (observations[i - 1].bbox_xyxy[0] + observations[i - 1].bbox_xyxy[2]) / 2
        cy1 = (observations[i - 1].bbox_xyxy[1] + observations[i - 1].bbox_xyxy[3]) / 2
        cx2 = (observations[i].bbox_xyxy[0] + observations[i].bbox_xyxy[2]) / 2
        cy2 = (observations[i].bbox_xyxy[1] + observations[i].bbox_xyxy[3]) / 2
        dist = math.sqrt((cx2 - cx1) ** 2 + (cy2 - cy1) ** 2)
        if dist > bbox_jump_threshold:
            bbox_jumps += 1

    # Continuity rate
    if len(timestamps) >= 2:
        total_duration = timestamps[-1] - timestamps[0]
        expected_frames = int(total_duration * expected_fps) + 1
        continuity = len(observations) / max(expected_frames, 1)
    else:
        continuity = 1.0

    return TrackDiagnostic(
        total_frames=int((timestamps[-1] - timestamps[0]) * expected_fps) + 1
        if len(timestamps) >= 2
        else len(observations),
        total_observations=len(observations),
        unique_track_ids=len(unique_ids),
        id_switches=id_switches,
        max_gap_frames=max_gap,
        gap_count=gap_count,
        bbox_jump_count=bbox_jumps,
        bbox_jump_threshold_pixels=bbox_jump_threshold,
        continuity_rate=min(1.0, continuity),
    )


def categorize_error(
    is_fall_gt: bool,
    is_fall_pred: bool,
    pose_diag: PoseDiagnostic | None,
    track_diag: TrackDiagnostic | None,
    max_classifier_prob: float | None = None,
    peak_velocity: float | None = None,
) -> tuple[str | None, str | None]:
    """Categorize the primary error source for a misclassification.

    Returns:
        (error_category, error_subcategory) or (None, None) if correct.
    """
    if is_fall_gt == is_fall_pred:
        return None, None

    # False Negative analysis (missed fall)
    if is_fall_gt and not is_fall_pred:
        if pose_diag and pose_diag.mean_confidence < 0.3:
            return "POSE", "low_keypoint_confidence"
        if pose_diag and not pose_diag.has_torso_vector:
            return "POSE", "missing_torso_keypoints"
        if track_diag and track_diag.id_switches > 0:
            return "TRACKING", "id_switch_during_fall"
        if track_diag and track_diag.gap_count > 2:
            return "TRACKING", "excessive_track_gaps"
        if max_classifier_prob is not None and max_classifier_prob < 0.3:
            return "TEMPORAL", "low_classifier_confidence"
        if peak_velocity is not None and peak_velocity < 0.2:
            return "CAMERA", "low_apparent_velocity"
        return "TEMPORAL", "threshold_not_reached"

    # False Positive analysis (false alarm)
    if not is_fall_gt and is_fall_pred:
        if peak_velocity is not None and peak_velocity > 0.5:
            return "TEMPORAL", "rapid_non_fall_movement"
        if max_classifier_prob is not None and max_classifier_prob > 0.8:
            return "TEMPORAL", "high_confidence_false_positive"
        return "TEMPORAL", "threshold_too_sensitive"

    return None, None
