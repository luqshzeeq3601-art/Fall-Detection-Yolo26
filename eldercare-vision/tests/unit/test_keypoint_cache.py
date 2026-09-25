from pathlib import Path

import pytest

from eldercare.fall_engine.cache.schema import (
    CachedFrame,
    CachedKeypointSequence,
    CachedPerson,
    KeypointCacheMetadata,
)
from eldercare.fall_engine.cache.serialization import (
    deserialize_sequence_from_json,
    keypoint_from_dict,
    keypoint_to_dict,
    sequence_from_observations,
    sequence_from_tracked_frames,
    sequence_to_observations,
    sequence_to_tracked_frames,
    serialize_sequence_to_json,
)
from eldercare.fall_engine.cache.storage import (
    load_keypoint_cache,
    save_keypoint_cache,
    validate_cache_provenance,
)
from eldercare.vision.pose.adapter import Keypoint, PersonPose
from eldercare.vision.tracking.tracker import TrackedFrame, TrackedPerson
from tests.fixtures.synthetic_fall_fixtures import (
    generate_fall_sequence,
)


def _make_dummy_keypoints() -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(x=100.0 + i, y=150.0 + i, confidence=0.9, present=True) for i in range(17)
    )


def _make_valid_metadata(*, total_frames: int = 1) -> KeypointCacheMetadata:
    return KeypointCacheMetadata(
        source_sample_id="urfd_fall_01",
        model_name="yolo26s-pose.pt",
        inference_library_version="ultralytics==8.3.0",
        extraction_timestamp="2026-09-23T12:00:00Z",
        total_frames=total_frames,
        inference_config={"imgsz": 640, "conf": 0.25},
        source_checksum="sha256:abcd1234",
        fps=30.0,
    )


class TestKeypointCacheMetadata:
    """Test provenance metadata validation and strict anti-leakage guards."""

    def test_valid_metadata_construction(self) -> None:
        meta = _make_valid_metadata(total_frames=5)
        assert meta.source_sample_id == "urfd_fall_01"
        assert meta.model_name == "yolo26s-pose.pt"
        assert meta.is_derived is True
        assert meta.is_ground_truth is False
        assert meta.fps == 30.0
        assert meta.total_frames == 5

    def test_reject_is_derived_false(self) -> None:
        with pytest.raises(ValueError, match="is_derived must be True"):
            KeypointCacheMetadata(
                source_sample_id="sample_1",
                model_name="yolo26s-pose.pt",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=1,
                is_derived=False,
            )

    def test_reject_is_ground_truth_true(self) -> None:
        with pytest.raises(ValueError, match="is_ground_truth must be False"):
            KeypointCacheMetadata(
                source_sample_id="sample_1",
                model_name="yolo26s-pose.pt",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=1,
                is_ground_truth=True,
            )

    def test_reject_empty_or_whitespace_strings(self) -> None:
        with pytest.raises(ValueError, match="source_sample_id"):
            KeypointCacheMetadata(
                source_sample_id="   ",
                model_name="yolo26s-pose.pt",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=1,
            )

        with pytest.raises(ValueError, match="model_name"):
            KeypointCacheMetadata(
                source_sample_id="sample_1",
                model_name="",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=1,
            )

    def test_reject_invalid_total_frames(self) -> None:
        with pytest.raises(ValueError, match="total_frames"):
            KeypointCacheMetadata(
                source_sample_id="sample_1",
                model_name="yolo26s-pose.pt",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=-1,
            )

    def test_reject_invalid_fps(self) -> None:
        with pytest.raises(ValueError, match="fps"):
            KeypointCacheMetadata(
                source_sample_id="sample_1",
                model_name="yolo26s-pose.pt",
                inference_library_version="8.3.0",
                extraction_timestamp="2026-09-23T12:00:00Z",
                total_frames=1,
                fps=-10.0,
            )


class TestKeypointCacheSchema:
    """Test CachedPerson, CachedFrame, and CachedKeypointSequence schemas."""

    def test_cached_person_valid(self) -> None:
        kps = _make_dummy_keypoints()
        person = CachedPerson(
            track_id=1,
            bbox_xyxy=(50.0, 60.0, 150.0, 200.0),
            detection_confidence=0.88,
            keypoints=kps,
        )
        assert person.track_id == 1
        assert len(person.keypoints) == 17
        assert person.bbox_xyxy == (50.0, 60.0, 150.0, 200.0)

    def test_cached_person_reject_invalid_bbox(self) -> None:
        kps = _make_dummy_keypoints()
        with pytest.raises(ValueError, match="bbox ordering violated"):
            CachedPerson(
                track_id=1,
                bbox_xyxy=(150.0, 60.0, 50.0, 200.0),  # x1 > x2
                detection_confidence=0.88,
                keypoints=kps,
            )

    def test_cached_person_reject_invalid_keypoint_count(self) -> None:
        with pytest.raises(ValueError, match="keypoints must hold exactly 17"):
            CachedPerson(
                track_id=1,
                bbox_xyxy=(50.0, 60.0, 150.0, 200.0),
                detection_confidence=0.88,
                keypoints=tuple(_make_dummy_keypoints()[:10]),
            )

    def test_cached_frame_valid(self) -> None:
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=1,
            bbox_xyxy=(50.0, 60.0, 150.0, 200.0),
            detection_confidence=0.88,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.0,
            image_width=1920,
            image_height=1080,
            persons=(p,),
        )
        assert frame.frame_index == 0
        assert frame.timestamp == 0.0
        assert len(frame.persons) == 1

    def test_sequence_frame_count_mismatch_fails_closed(self) -> None:
        meta = _make_valid_metadata(total_frames=2)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=1,
            bbox_xyxy=(50.0, 60.0, 150.0, 200.0),
            detection_confidence=0.88,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.0,
            image_width=1920,
            image_height=1080,
            persons=(p,),
        )
        with pytest.raises(ValueError, match="frame count mismatch"):
            CachedKeypointSequence(metadata=meta, frames=(frame,))


class TestKeypointCacheSerialization:
    """Test JSON serialization, deserialization, and domain contract conversion."""

    def test_keypoint_dict_roundtrip(self) -> None:
        kp = Keypoint(x=123.4, y=567.8, confidence=0.95, present=True)
        d = keypoint_to_dict(kp)
        restored = keypoint_from_dict(d)
        assert restored == kp

    def test_sequence_json_roundtrip(self) -> None:
        meta = _make_valid_metadata(total_frames=1)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=2,
            bbox_xyxy=(10.0, 20.0, 100.0, 200.0),
            detection_confidence=0.92,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.5,
            image_width=1280,
            image_height=720,
            persons=(p,),
        )
        seq = CachedKeypointSequence(metadata=meta, frames=(frame,))

        json_str = serialize_sequence_to_json(seq)
        assert isinstance(json_str, str)
        restored = deserialize_sequence_from_json(json_str)

        assert restored.metadata.source_sample_id == "urfd_fall_01"
        assert restored.metadata.total_frames == 1
        assert len(restored.frames) == 1
        assert restored.frames[0].persons[0].track_id == 2
        assert restored.frames[0].persons[0].bbox_xyxy == (10.0, 20.0, 100.0, 200.0)

    def test_deserialize_malformed_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid JSON string"):
            deserialize_sequence_from_json("{not valid json")

    def test_sequence_from_and_to_observations(self) -> None:
        obs_seq = generate_fall_sequence(fps=30.0, camera_id="cam_01")
        meta = _make_valid_metadata(total_frames=len(obs_seq))

        cached_seq = sequence_from_observations(meta, obs_seq)
        assert len(cached_seq.frames) == len(obs_seq)

        restored_obs = sequence_to_observations(cached_seq, camera_id="cam_01")
        assert len(restored_obs) == len(obs_seq)

        for orig, restored in zip(obs_seq, restored_obs, strict=True):
            assert orig.timestamp == pytest.approx(restored.timestamp, rel=1e-5)
            assert orig.track_id == restored.track_id
            assert orig.bbox_xyxy == restored.bbox_xyxy

    def test_sequence_from_and_to_tracked_frames(self) -> None:
        kps = _make_dummy_keypoints()
        pose = PersonPose(
            bbox_xyxy=(10.0, 20.0, 100.0, 200.0),
            detection_confidence=0.95,
            keypoints=kps,
        )
        tracked_person = TrackedPerson(person=pose, track_id=42)
        tracked_frame = TrackedFrame(image_width=640, image_height=480, persons=(tracked_person,))
        frames = [(0.0, tracked_frame), (0.033, tracked_frame)]

        meta = _make_valid_metadata(total_frames=2)
        cached_seq = sequence_from_tracked_frames(meta, frames)
        assert len(cached_seq.frames) == 2

        restored_frames = sequence_to_tracked_frames(cached_seq)
        assert len(restored_frames) == 2
        assert restored_frames[0][0] == 0.0
        assert restored_frames[0][1].persons[0].track_id == 42
        assert restored_frames[0][1].persons[0].person.bbox_xyxy == (10.0, 20.0, 100.0, 200.0)


class TestKeypointCacheStorage:
    """Test disk operations, atomic replacement, and provenance verification."""

    def test_save_and_load_uncompressed(self, tmp_path: Path) -> None:
        meta = _make_valid_metadata(total_frames=1)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=1,
            bbox_xyxy=(10.0, 20.0, 100.0, 200.0),
            detection_confidence=0.9,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.0,
            image_width=640,
            image_height=480,
            persons=(p,),
        )
        seq = CachedKeypointSequence(metadata=meta, frames=(frame,))

        file_path = tmp_path / "seq.json"
        saved_path = save_keypoint_cache(seq, file_path)
        assert saved_path.is_file()

        loaded_seq = load_keypoint_cache(saved_path)
        assert loaded_seq.metadata.source_sample_id == "urfd_fall_01"
        assert len(loaded_seq.frames) == 1

    def test_save_and_load_gzip(self, tmp_path: Path) -> None:
        meta = _make_valid_metadata(total_frames=1)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=1,
            bbox_xyxy=(10.0, 20.0, 100.0, 200.0),
            detection_confidence=0.9,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.0,
            image_width=640,
            image_height=480,
            persons=(p,),
        )
        seq = CachedKeypointSequence(metadata=meta, frames=(frame,))

        gz_path = tmp_path / "seq.json.gz"
        saved_path = save_keypoint_cache(seq, gz_path, compress=True)
        assert saved_path.is_file()

        loaded_seq = load_keypoint_cache(saved_path)
        assert loaded_seq.metadata.source_sample_id == "urfd_fall_01"
        assert len(loaded_seq.frames) == 1

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_keypoint_cache(tmp_path / "missing.json")

    def test_validate_cache_provenance(self) -> None:
        meta = _make_valid_metadata(total_frames=1)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=1,
            bbox_xyxy=(10.0, 20.0, 100.0, 200.0),
            detection_confidence=0.9,
            keypoints=kps,
        )
        frame = CachedFrame(
            frame_index=0,
            timestamp=0.0,
            image_width=640,
            image_height=480,
            persons=(p,),
        )
        seq = CachedKeypointSequence(metadata=meta, frames=(frame,))

        assert (
            validate_cache_provenance(
                seq, expected_model="yolo26s-pose.pt", expected_sample_id="urfd_fall_01"
            )
            is True
        )
        assert validate_cache_provenance(seq, expected_model="wrong-model.pt") is False
        assert validate_cache_provenance(seq, expected_sample_id="wrong_sample") is False

    def test_save_load_npz_roundtrip(self, tmp_path: Path) -> None:
        """Verify atomic write and deserialization for .npz NumPy archive backend."""
        meta = _make_valid_metadata(total_frames=2)
        kps = _make_dummy_keypoints()
        p = CachedPerson(
            track_id=42,
            bbox_xyxy=(15.0, 25.0, 150.0, 250.0),
            detection_confidence=0.92,
            keypoints=kps,
        )
        f0 = CachedFrame(frame_index=0, timestamp=0.0, image_width=640, image_height=480, persons=(p,))
        f1 = CachedFrame(frame_index=1, timestamp=0.066, image_width=640, image_height=480, persons=(p,))
        seq = CachedKeypointSequence(metadata=meta, frames=(f0, f1))

        npz_path = tmp_path / "seq.npz"
        saved_path = save_keypoint_cache(seq, npz_path)
        assert saved_path.is_file()

        loaded_seq = load_keypoint_cache(saved_path)
        assert loaded_seq.metadata.source_sample_id == "urfd_fall_01"
        assert len(loaded_seq.frames) == 2
        assert loaded_seq.frames[0].persons[0].track_id == 42
        assert loaded_seq.frames[0].persons[0].detection_confidence == pytest.approx(0.92, abs=1e-3)
        assert len(loaded_seq.frames[0].persons[0].keypoints) == 17
