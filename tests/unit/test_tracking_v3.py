"""Unit tests for V3 tracking module — track stitching and quality assessment."""

from __future__ import annotations

from eldercare.fall_engine.tracking_v3 import (
    TrackStitchConfig,
    TrackStitcher,
    compute_track_quality,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_obs(
    track_id: int = 1,
    timestamp: float = 0.0,
    bbox: tuple[float, float, float, float] = (100.0, 100.0, 200.0, 300.0),
    cam_id: str = "cam1",
    kpt_conf: float = 0.8,
) -> TrackObservation:
    """Create a synthetic TrackObservation for testing."""
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1

    keypoints = []
    # Generate 17 COCO keypoints in plausible positions
    kpt_positions = [
        (0.5, 0.1),  # nose
        (0.45, 0.08),  # left_eye
        (0.55, 0.08),  # right_eye
        (0.4, 0.1),  # left_ear
        (0.6, 0.1),  # right_ear
        (0.35, 0.3),  # left_shoulder
        (0.65, 0.3),  # right_shoulder
        (0.25, 0.5),  # left_elbow
        (0.75, 0.5),  # right_elbow
        (0.2, 0.7),  # left_wrist
        (0.8, 0.7),  # right_wrist
        (0.4, 0.55),  # left_hip
        (0.6, 0.55),  # right_hip
        (0.35, 0.75),  # left_knee
        (0.65, 0.75),  # right_knee
        (0.3, 0.95),  # left_ankle
        (0.7, 0.95),  # right_ankle
    ]
    for rx, ry in kpt_positions:
        keypoints.append(
            Keypoint(
                x=x1 + rx * w,
                y=y1 + ry * h,
                confidence=kpt_conf,
                present=True,
            )
        )

    return TrackObservation(
        camera_id=cam_id,
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=bbox,
        detection_confidence=0.9,
        keypoints=tuple(keypoints),
        image_width=640,
        image_height=480,
    )


class TestTrackQuality:
    """Tests for track quality computation."""

    def test_empty_observations(self) -> None:
        metrics = compute_track_quality([], "cam1", 1)
        assert metrics.total_observations == 0
        assert metrics.continuity_rate == 0.0

    def test_single_observation(self) -> None:
        obs = [_make_obs(timestamp=0.0)]
        metrics = compute_track_quality(obs, "cam1", 1)
        assert metrics.total_observations == 1
        assert metrics.continuity_rate == 1.0

    def test_continuous_track(self) -> None:
        obs = [_make_obs(timestamp=i / 30.0) for i in range(30)]
        metrics = compute_track_quality(obs, "cam1", 1)
        assert metrics.total_observations == 30
        assert metrics.gap_count == 0
        assert metrics.continuity_rate >= 0.9

    def test_track_with_gaps(self) -> None:
        # Create track with a 0.5s gap
        obs = [_make_obs(timestamp=i / 30.0) for i in range(15)]
        obs += [_make_obs(timestamp=0.5 + i / 30.0 + 0.5) for i in range(15)]
        metrics = compute_track_quality(obs, "cam1", 1)
        assert metrics.gap_count >= 1
        assert metrics.continuity_rate < 1.0

    def test_reliable_track(self) -> None:
        obs = [_make_obs(timestamp=i / 30.0) for i in range(30)]
        metrics = compute_track_quality(obs, "cam1", 1)
        assert metrics.is_reliable


class TestTrackStitcher:
    """Tests for track stitching."""

    def test_stitch_close_tracks(self) -> None:
        config = TrackStitchConfig(
            max_gap_frames=15,
            max_gap_seconds=1.0,
            spatial_threshold=50.0,
            keypoint_similarity_threshold=0.5,
        )
        stitcher = TrackStitcher(config)

        # Register lost track
        lost_obs = [_make_obs(track_id=1, timestamp=i / 30.0) for i in range(10)]
        stitcher.register_lost_track(1, lost_obs)

        # Try to stitch new track appearing nearby shortly after
        new_obs = [
            _make_obs(track_id=2, timestamp=0.4, bbox=(105.0, 105.0, 205.0, 305.0)),
            _make_obs(track_id=2, timestamp=0.433, bbox=(106.0, 106.0, 206.0, 306.0)),
        ]
        result = stitcher.try_stitch(2, new_obs)
        assert result == 1  # Should stitch to track 1

    def test_no_stitch_far_tracks(self) -> None:
        stitcher = TrackStitcher()
        lost_obs = [_make_obs(track_id=1, timestamp=i / 30.0) for i in range(10)]
        stitcher.register_lost_track(1, lost_obs)

        # New track very far away
        new_obs = [
            _make_obs(track_id=2, timestamp=0.4, bbox=(400.0, 400.0, 500.0, 600.0)),
            _make_obs(track_id=2, timestamp=0.433, bbox=(401.0, 401.0, 501.0, 601.0)),
        ]
        result = stitcher.try_stitch(2, new_obs)
        assert result is None  # Should NOT stitch

    def test_canonical_track_id(self) -> None:
        stitcher = TrackStitcher()
        stitcher._stitch_map[2] = 1
        stitcher._stitch_map[3] = 2
        assert stitcher.get_canonical_track_id(3) == 1
        assert stitcher.get_canonical_track_id(1) == 1

    def test_cleanup_expired(self) -> None:
        stitcher = TrackStitcher()
        lost_obs = [_make_obs(track_id=1, timestamp=0.0)]
        stitcher.register_lost_track(1, lost_obs * 5)
        removed = stitcher.cleanup_expired(10.0, max_age_seconds=5.0)
        assert removed == 1
