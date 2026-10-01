"""Unit tests for Phase 11.8 V5 Pose Extraction and Resampling Engine."""

from pathlib import Path

import pytest

from eldercare.fall_engine.cache.schema import (
    CachedFrame,
    CachedKeypointSequence,
    CachedPerson,
    KeypointCacheMetadata,
)
from eldercare.fall_engine.cache.storage import load_keypoint_cache, save_keypoint_cache
from eldercare.vision.pose.adapter import Keypoint
from scripts.dataset.extract_pose_cache import resample_keypoints_to_15hz


def _make_dummy_keypoints() -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(x=100.0 + i, y=150.0 + i, confidence=0.9, present=True) for i in range(17)
    )


def test_resample_keypoints_to_15hz_uniform() -> None:
    """Verify resampling 30fps frames to 15fps creates correct timestamps."""
    kps = _make_dummy_keypoints()
    p = CachedPerson(
        track_id=1, bbox_xyxy=(10.0, 20.0, 100.0, 200.0), detection_confidence=0.9, keypoints=kps
    )

    # 30 fps frames: dt = 0.0333s for 1 second (31 frames from t=0.0 to 1.0)
    raw_frames = [
        CachedFrame(
            frame_index=i,
            timestamp=i * (1.0 / 30.0),
            image_width=640,
            image_height=480,
            persons=(p,),
        )
        for i in range(31)
    ]

    resampled = resample_keypoints_to_15hz(raw_frames, target_fps=15.0)

    # 15 fps for 1 second should produce 16 frames (0.0s, 0.0667s, ..., 1.0s)
    assert len(resampled) == 16
    assert resampled[0].timestamp == 0.0
    assert pytest.approx(resampled[-1].timestamp, abs=1e-3) == 1.0
    assert all(len(f.persons) == 1 for f in resampled)


def test_resample_keypoints_missing_frame_preserves_mask() -> None:
    """Verify that gaps in raw frames produce empty CachedFrame without fabricating keypoints."""
    kps = _make_dummy_keypoints()
    p = CachedPerson(
        track_id=1, bbox_xyxy=(10.0, 20.0, 100.0, 200.0), detection_confidence=0.9, keypoints=kps
    )

    # Sequence with a big gap: frame at 0.0s and frame at 1.0s (nothing in between)
    f0 = CachedFrame(frame_index=0, timestamp=0.0, image_width=640, image_height=480, persons=(p,))
    f1 = CachedFrame(frame_index=30, timestamp=1.0, image_width=640, image_height=480, persons=(p,))

    resampled = resample_keypoints_to_15hz([f0, f1], target_fps=15.0)

    assert len(resampled) == 16
    assert len(resampled[0].persons) == 1
    assert len(resampled[-1].persons) == 1

    # Intermediate frames must have empty persons (never fabricated!)
    for f in resampled[1:-1]:
        assert f.persons == ()


def test_npz_cache_roundtrip_with_missing_keypoints(tmp_path: Path) -> None:
    """Verify that keypoints with present=False, x=None, y=None roundtrip through .npz perfectly."""
    kps_list = list(_make_dummy_keypoints())
    # Mask out keypoints 3 and 7
    kps_list[3] = Keypoint(x=None, y=None, confidence=0.05, present=False)
    kps_list[7] = Keypoint(x=None, y=None, confidence=0.12, present=False)

    p = CachedPerson(
        track_id=10,
        bbox_xyxy=(50.0, 60.0, 150.0, 250.0),
        detection_confidence=0.88,
        keypoints=tuple(kps_list),
    )
    f0 = CachedFrame(frame_index=0, timestamp=0.0, image_width=640, image_height=480, persons=(p,))

    meta = KeypointCacheMetadata(
        source_sample_id="test_masked_seq",
        model_name="yolo26s-pose.pt",
        inference_library_version="ultralytics==8.3.0",
        extraction_timestamp="2026-09-25T12:00:00Z",
        total_frames=1,
        inference_config={"imgsz": 640},
        source_checksum="sha256:1234abcd",
        fps=15.0,
    )
    seq = CachedKeypointSequence(metadata=meta, frames=(f0,))

    target_npz = tmp_path / "test_masked.npz"
    saved = save_keypoint_cache(seq, target_npz)
    assert saved.is_file()

    loaded = load_keypoint_cache(saved)
    assert len(loaded.frames) == 1
    loaded_p = loaded.frames[0].persons[0]

    assert loaded_p.keypoints[3].present is False
    assert loaded_p.keypoints[3].x is None
    assert loaded_p.keypoints[3].y is None
    assert loaded_p.keypoints[3].confidence == pytest.approx(0.05, abs=1e-3)

    assert loaded_p.keypoints[7].present is False
    assert loaded_p.keypoints[7].x is None
    assert loaded_p.keypoints[7].y is None
    assert loaded_p.keypoints[7].confidence == pytest.approx(0.12, abs=1e-3)

    assert loaded_p.keypoints[0].present is True
    assert loaded_p.keypoints[0].x == pytest.approx(100.0, abs=1e-3)
