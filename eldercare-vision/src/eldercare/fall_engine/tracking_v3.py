"""V3 Track Stitching and Quality Assessment (Phase 11.6).

Provides spatial/keypoint-aware track stitching for short gaps, track quality
scoring, and ID-switch detection. Designed to improve fall-event track continuity
without blindly preserving state across different people.

Safety constraint: multi-person adversarial tests must prevent identity leakage.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class TrackQualityMetrics:
    """Quality metrics for a single tracked person's observation history."""

    track_id: int
    camera_id: str
    total_observations: int
    duration_seconds: float
    gap_count: int
    max_gap_seconds: float
    total_gap_seconds: float
    mean_keypoint_confidence: float
    mean_keypoint_count: float
    bbox_stability: float  # low = stable, high = jittery
    continuity_rate: float  # observations / expected_observations

    @property
    def is_reliable(self) -> bool:
        """Track is reliable enough for fall detection."""
        return (
            self.total_observations >= 5
            and self.continuity_rate >= 0.7
            and self.mean_keypoint_confidence >= 0.25
            and self.mean_keypoint_count >= 6
        )


@dataclass
class TrackStitchCandidate:
    """A candidate for stitching two track segments together."""

    lost_track_id: int
    new_track_id: int
    gap_frames: int
    gap_seconds: float
    spatial_distance: float
    keypoint_similarity: float
    confidence_score: float


@dataclass
class TrackStitchConfig:
    """Configuration for track stitching."""

    max_gap_frames: int = 15
    max_gap_seconds: float = 1.0
    spatial_threshold: float = 50.0
    keypoint_similarity_threshold: float = 0.6
    min_observations_before_stitch: int = 3


class TrackStitcher:
    """Stitches broken tracks across short gaps using spatial and keypoint similarity.

    SAFETY: Never blindly preserves state across different people.
    Requires both spatial proximity AND keypoint configuration similarity.
    """

    def __init__(self, config: TrackStitchConfig | None = None) -> None:
        self.config = config or TrackStitchConfig()
        self._lost_tracks: dict[int, list[TrackObservation]] = {}
        self._stitch_map: dict[int, int] = {}  # new_id -> original_id
        self._stitch_log: list[TrackStitchCandidate] = []

    def register_lost_track(
        self,
        track_id: int,
        last_observations: list[TrackObservation],
    ) -> None:
        """Register a track that has been lost (no detection for buffer frames)."""
        if len(last_observations) >= self.config.min_observations_before_stitch:
            self._lost_tracks[track_id] = last_observations[-10:]  # Keep last 10

    def try_stitch(
        self,
        new_track_id: int,
        new_observations: list[TrackObservation],
    ) -> int | None:
        """Try to stitch a new track to a lost track.

        Returns:
            Original track ID if stitched, None otherwise.
        """
        if len(new_observations) < 2:
            return None

        new_obs = new_observations[0]
        best_match: TrackStitchCandidate | None = None
        best_score = 0.0

        for lost_id, lost_obs_list in list(self._lost_tracks.items()):
            if not lost_obs_list:
                continue

            last_lost = lost_obs_list[-1]

            # Time gap check
            gap_sec = new_obs.timestamp - last_lost.timestamp
            if gap_sec > self.config.max_gap_seconds or gap_sec < 0:
                continue

            gap_frames = int(gap_sec * 30)  # Approximate
            if gap_frames > self.config.max_gap_frames:
                continue

            # Spatial distance check (bbox center)
            lost_cx = (last_lost.bbox_xyxy[0] + last_lost.bbox_xyxy[2]) / 2
            lost_cy = (last_lost.bbox_xyxy[1] + last_lost.bbox_xyxy[3]) / 2
            new_cx = (new_obs.bbox_xyxy[0] + new_obs.bbox_xyxy[2]) / 2
            new_cy = (new_obs.bbox_xyxy[1] + new_obs.bbox_xyxy[3]) / 2
            spatial_dist = math.sqrt((new_cx - lost_cx) ** 2 + (new_cy - lost_cy) ** 2)

            if spatial_dist > self.config.spatial_threshold:
                continue

            # Keypoint similarity check
            kpt_sim = _compute_keypoint_similarity(last_lost, new_obs)
            if kpt_sim < self.config.keypoint_similarity_threshold:
                continue

            # Compute composite stitch confidence
            spatial_score = max(0.0, 1.0 - spatial_dist / self.config.spatial_threshold)
            gap_score = max(0.0, 1.0 - gap_sec / self.config.max_gap_seconds)
            confidence = 0.4 * spatial_score + 0.4 * kpt_sim + 0.2 * gap_score

            candidate = TrackStitchCandidate(
                lost_track_id=lost_id,
                new_track_id=new_track_id,
                gap_frames=gap_frames,
                gap_seconds=gap_sec,
                spatial_distance=spatial_dist,
                keypoint_similarity=kpt_sim,
                confidence_score=confidence,
            )

            if confidence > best_score:
                best_score = confidence
                best_match = candidate

        if best_match is not None and best_score >= 0.5:
            self._stitch_map[new_track_id] = best_match.lost_track_id
            self._stitch_log.append(best_match)
            # Remove from lost tracks
            self._lost_tracks.pop(best_match.lost_track_id, None)
            return best_match.lost_track_id

        return None

    def get_canonical_track_id(self, track_id: int) -> int:
        """Get the original (canonical) track ID after stitching."""
        seen: set[int] = set()
        current = track_id
        while current in self._stitch_map and current not in seen:
            seen.add(current)
            current = self._stitch_map[current]
        return current

    def cleanup_expired(self, current_timestamp: float, max_age_seconds: float = 5.0) -> int:
        """Remove lost tracks older than max_age_seconds."""
        expired = [
            tid
            for tid, obs_list in self._lost_tracks.items()
            if obs_list and (current_timestamp - obs_list[-1].timestamp) > max_age_seconds
        ]
        for tid in expired:
            del self._lost_tracks[tid]
        return len(expired)

    @property
    def stitch_log(self) -> list[TrackStitchCandidate]:
        """Return the log of all stitch operations."""
        return list(self._stitch_log)


def compute_track_quality(
    observations: list[TrackObservation],
    camera_id: str,
    track_id: int,
    expected_fps: float = 30.0,
) -> TrackQualityMetrics:
    """Compute quality metrics for a track's observation history."""
    if not observations:
        return TrackQualityMetrics(
            track_id=track_id,
            camera_id=camera_id,
            total_observations=0,
            duration_seconds=0.0,
            gap_count=0,
            max_gap_seconds=0.0,
            total_gap_seconds=0.0,
            mean_keypoint_confidence=0.0,
            mean_keypoint_count=0.0,
            bbox_stability=float("inf"),
            continuity_rate=0.0,
        )

    timestamps = [obs.timestamp for obs in observations]
    duration = timestamps[-1] - timestamps[0] if len(timestamps) >= 2 else 0.0

    # Gap analysis
    expected_dt = 1.0 / expected_fps
    gaps: list[float] = []
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        if dt > expected_dt * 2:  # Gap if more than 2x expected interval
            gaps.append(dt)

    # Keypoint statistics
    kpt_confs: list[float] = []
    kpt_counts: list[int] = []
    for obs in observations:
        present = [
            k for k in obs.keypoints
            if k.present and k.x is not None and k.y is not None
        ]
        kpt_counts.append(len(present))
        if present:
            kpt_confs.append(
                sum(k.confidence for k in present) / len(present)
            )

    # Bbox stability (center displacement variance)
    centers: list[tuple[float, float]] = []
    for obs in observations:
        cx = (obs.bbox_xyxy[0] + obs.bbox_xyxy[2]) / 2
        cy = (obs.bbox_xyxy[1] + obs.bbox_xyxy[3]) / 2
        centers.append((cx, cy))

    if len(centers) >= 2:
        displacements: list[float] = []
        for i in range(1, len(centers)):
            dx = centers[i][0] - centers[i - 1][0]
            dy = centers[i][1] - centers[i - 1][1]
            displacements.append(math.sqrt(dx * dx + dy * dy))
        mean_disp = sum(displacements) / len(displacements) if displacements else 0.0
        var_disp = (
            sum((d - mean_disp) ** 2 for d in displacements) / len(displacements)
            if displacements
            else 0.0
        )
        bbox_stability = math.sqrt(var_disp)
    else:
        bbox_stability = 0.0

    # Continuity rate
    if duration > 0:
        expected_obs = int(duration * expected_fps) + 1
        continuity = len(observations) / max(expected_obs, 1)
    else:
        continuity = 1.0

    return TrackQualityMetrics(
        track_id=track_id,
        camera_id=camera_id,
        total_observations=len(observations),
        duration_seconds=duration,
        gap_count=len(gaps),
        max_gap_seconds=max(gaps) if gaps else 0.0,
        total_gap_seconds=sum(gaps),
        mean_keypoint_confidence=sum(kpt_confs) / len(kpt_confs) if kpt_confs else 0.0,
        mean_keypoint_count=sum(kpt_counts) / len(kpt_counts) if kpt_counts else 0.0,
        bbox_stability=bbox_stability,
        continuity_rate=min(1.0, continuity),
    )


def _compute_keypoint_similarity(
    obs_a: TrackObservation,
    obs_b: TrackObservation,
) -> float:
    """Compute keypoint configuration similarity between two observations.

    Uses normalized keypoint positions relative to bbox to compare body pose.
    Returns similarity in [0, 1].
    """
    kpts_a = obs_a.keypoints
    kpts_b = obs_b.keypoints

    # Normalize keypoints to bbox-relative coordinates
    ax1, ay1, ax2, ay2 = obs_a.bbox_xyxy
    bx1, by1, bx2, by2 = obs_b.bbox_xyxy
    aw = max(ax2 - ax1, 1e-6)
    ah = max(ay2 - ay1, 1e-6)
    bw = max(bx2 - bx1, 1e-6)
    bh = max(by2 - by1, 1e-6)

    matches = 0
    total = 0
    total_dist = 0.0

    for ka, kb in zip(kpts_a, kpts_b, strict=False):
        a_valid = ka.present and ka.x is not None and ka.y is not None
        b_valid = kb.present and kb.x is not None and kb.y is not None

        if a_valid and b_valid:
            total += 1
            assert ka.x is not None and ka.y is not None
            assert kb.x is not None and kb.y is not None
            # Normalize to [0, 1] relative to bbox
            na_x = (ka.x - ax1) / aw
            na_y = (ka.y - ay1) / ah
            nb_x = (kb.x - bx1) / bw
            nb_y = (kb.y - by1) / bh
            dist = math.sqrt((na_x - nb_x) ** 2 + (na_y - nb_y) ** 2)
            total_dist += dist
            if dist < 0.3:  # Threshold for "matching" keypoint position
                matches += 1

    if total == 0:
        return 0.0

    match_ratio = matches / total
    mean_dist = total_dist / total
    dist_score = max(0.0, 1.0 - mean_dist)

    return 0.6 * match_ratio + 0.4 * dist_score
