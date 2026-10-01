"""Integration tests for Temporal Fall Engine feature extraction pipeline (P4-002).

Tests end-to-end flow from TrackObservation sequences and TrackHistory stores
into temporal motion feature extraction across realistic multi-person and ADL scenarios.
"""

from __future__ import annotations

from eldercare.fall_engine.features import extract_temporal_features
from tests.fixtures.synthetic_fall_fixtures import (
    LEFT_ANKLE,
    LEFT_KNEE,
    RIGHT_ANKLE,
    RIGHT_KNEE,
    generate_bending_sequence,
    generate_fall_sequence,
    generate_walking_sequence,
    mask_missing_keypoints,
    populate_history_from_sequence,
)


def test_end_to_end_history_to_features() -> None:
    """Verify extracting features directly from TrackHistory snapshots."""
    walk_seq = generate_walking_sequence(
        camera_id="cam-front", track_id=10, duration_sec=2.0, fps=15.0
    )
    history = populate_history_from_sequence(walk_seq)

    snap = history.snapshot("cam-front", 10)
    feats = extract_temporal_features(snap, window_seconds=1.5)

    assert feats.observation_count >= 15
    assert feats.current_geometry.aspect_ratio > 2.0
    assert abs(feats.normalized_vertical_velocity) < 0.2


def test_multi_person_temporal_isolation() -> None:
    """Verify temporal features for multiple concurrent people remain completely isolated."""
    # Person 1 walks normally
    p1_seq = generate_walking_sequence(camera_id="cam-01", track_id=1, duration_sec=3.0, fps=15.0)
    # Person 2 falls
    p2_seq = generate_fall_sequence(
        camera_id="cam-01",
        track_id=2,
        duration_sec=3.0,
        fps=15.0,
        fall_start_sec=1.0,
    )

    # Populate both into single shared TrackHistory
    combined_seq = []
    for obs1, obs2 in zip(p1_seq, p2_seq, strict=True):
        combined_seq.extend([obs1, obs2])

    history = populate_history_from_sequence(combined_seq)

    # Extract features for Track 1 (walking)
    snap1 = history.snapshot("cam-01", 1)
    feats1 = extract_temporal_features(snap1, window_seconds=1.5)
    assert feats1.current_geometry.aspect_ratio > 2.0
    assert feats1.low_posture_duration_seconds == 0.0

    # Extract features for Track 2 (fallen)
    snap2 = history.snapshot("cam-01", 2)
    feats2 = extract_temporal_features(snap2, window_seconds=1.5)
    assert feats2.current_geometry.aspect_ratio < 0.5
    assert feats2.low_posture_duration_seconds > 1.0


def test_occluded_lower_body_fall_features() -> None:
    """Verify fall feature extraction when lower limbs are occluded by furniture."""
    raw_fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=1.0)
    # Mask out knees and ankles across the entire sequence
    occluded_seq = [
        mask_missing_keypoints(obs, [LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE])
        for obs in raw_fall_seq
    ]

    history = populate_history_from_sequence(occluded_seq)
    snap = history.snapshot("cam-01", 1)

    # Feature extraction still works via hip/shoulder midpoints and bbox
    descent_feats = extract_temporal_features(snap[:20], window_seconds=0.5)
    assert descent_feats.normalized_peak_vertical_velocity > 0.8
    assert descent_feats.current_geometry.keypoints_present_count == 13

    floor_feats = extract_temporal_features(snap, window_seconds=1.5)
    assert floor_feats.low_posture_duration_seconds > 1.0


def test_bending_vs_fall_feature_discrimination() -> None:
    """Verify feature extractor provides distinct signatures between bending and falling."""
    bend_seq = generate_bending_sequence(duration_sec=3.0, fps=15.0, bend_start_sec=0.5)
    fall_seq = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)

    # At t=2.5s:
    # Bending person has recovered to upright
    bend_feats = extract_temporal_features(bend_seq, window_seconds=1.5)
    assert bend_feats.current_geometry.aspect_ratio > 1.8
    assert bend_feats.low_posture_duration_seconds == 0.0

    # Fallen person is lying on floor
    fall_feats = extract_temporal_features(fall_seq, window_seconds=1.5)
    assert fall_feats.current_geometry.aspect_ratio < 0.5
    assert fall_feats.low_posture_duration_seconds > 1.0
