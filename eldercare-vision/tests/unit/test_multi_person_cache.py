"""Tests for multi-person pose caches, tracklet stitching and fall-subject selection.

Verifies:
1. NPZ caches keep every person per frame and round-trip their track ids.
2. Legacy single-person NPZ caches still load (one person per frame).
3. OnlineTrackStitcher continues a lost track with a nearby new id, not a far one.
4. The pipeline replay emits observations for every tracked person.
5. Training picks the track that falls as the labelled subject; bystanders are not.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eldercare.fall_engine.cache.schema import (
    CachedFrame,
    CachedKeypointSequence,
    CachedPerson,
    KeypointCacheMetadata,
)
from eldercare.fall_engine.cache.storage import load_keypoint_cache, save_keypoint_cache
from eldercare.fall_engine.learned_classifier.training_v5 import (
    load_dataset_samples_from_cache,
    load_track_arrays,
    select_subject_track,
)
from eldercare.fall_engine.pipeline_v6_1 import observations_from_cached_sequence
from eldercare.fall_engine.track_stitching import OnlineTrackStitcher
from eldercare.vision.pose.adapter import Keypoint


def _person(track_id: int, x: float, hip_y: float, height: float) -> CachedPerson:
    """Crude upright/lying skeleton: keypoints spread vertically over ``height``."""
    top = hip_y - height * 0.55
    kps = tuple(
        Keypoint(x=x + (i % 2) * 10.0, y=top + height * i / 16.0, confidence=0.9, present=True)
        for i in range(17)
    )
    kps = kps[:11] + (
        Keypoint(x=x - 10.0, y=hip_y, confidence=0.9, present=True),
        Keypoint(x=x + 10.0, y=hip_y, confidence=0.9, present=True),
    ) + kps[13:]
    return CachedPerson(
        track_id=track_id,
        bbox_xyxy=(x - 30.0, top, x + 30.0, top + height),
        detection_confidence=0.9,
        keypoints=kps,
    )


def _sequence(frames: list[tuple[CachedPerson, ...]]) -> CachedKeypointSequence:
    meta = KeypointCacheMetadata(
        source_sample_id="seq",
        model_name="yolo26s-pose.pt",
        inference_library_version="test",
        extraction_timestamp="2026-09-30T00:00:00+00:00",
        total_frames=len(frames),
        inference_config={},
        source_checksum="sha256:0",
        fps=15.0,
        schema_version="6.2.0",
        is_derived=True,
        is_ground_truth=False,
    )
    return CachedKeypointSequence(
        metadata=meta,
        frames=tuple(
            CachedFrame(
                frame_index=i, timestamp=i / 15.0, image_width=640, image_height=480, persons=p
            )
            for i, p in enumerate(frames)
        ),
    )


def _fall_with_bystander(t_len: int = 60, fragment_at: int | None = None) -> CachedKeypointSequence:
    """Subject (id 1) falls between frames 15 and 30; bystander (id 2) sits still.

    With ``fragment_at``, the tracker re-issues the subject as id 3 from that frame.
    """
    frames = []
    for t in range(t_len):
        prog = min(1.0, max(0.0, (t - 15) / 15.0))
        subject_id = 3 if fragment_at is not None and t >= fragment_at else 1
        subject = _person(subject_id, 200.0, 250.0 + 150.0 * prog, 200.0 - 150.0 * prog)
        bystander = _person(2, 520.0, 300.0, 160.0)
        frames.append((bystander, subject))  # bystander first, like the cam2 bug
    return _sequence(frames)


def test_npz_cache_keeps_every_person(tmp_path: Path):
    seq = _fall_with_bystander(10)
    loaded = load_keypoint_cache(save_keypoint_cache(seq, tmp_path / "mp.npz"))
    assert [len(f.persons) for f in loaded.frames] == [2] * 10
    assert {p.track_id for p in loaded.frames[0].persons} == {1, 2}
    assert loaded.frames[3].persons[1].bbox_xyxy == seq.frames[3].persons[1].bbox_xyxy


def test_legacy_single_person_npz_still_loads(tmp_path: Path):
    t_len = 4
    np.savez(
        tmp_path / "legacy.npz",
        keypoints=np.zeros((t_len, 17, 3), dtype=np.float32),
        presents=np.ones((t_len, 17), dtype=bool),
        bboxes=np.tile(np.array([0, 0, 10, 20], dtype=np.float32), (t_len, 1)),
        timestamps=np.arange(t_len) / 15.0,
        frame_indices=np.arange(t_len, dtype=np.int32),
        confidences=np.array([0.9, 0.0, 0.9, 0.9], dtype=np.float32),
        track_ids=np.array([1, -1, 1, 1], dtype=np.int32),
        dims=np.tile([640, 480], (t_len, 1)),
        metadata_json=np.array(
            '{"source_sample_id": "l", "model_name": "m", "inference_library_version": "v",'
            ' "extraction_timestamp": "2026-09-29T00:00:00+00:00", "total_frames": 4,'
            ' "inference_config": {}, "source_checksum": "sha256:0", "fps": 15.0,'
            ' "schema_version": "6.0.0", "is_derived": true, "is_ground_truth": false}'
        ),
    )
    loaded = load_keypoint_cache(tmp_path / "legacy.npz")
    assert [len(f.persons) for f in loaded.frames] == [1, 1, 1, 1]  # zero keypoints present
    assert loaded.frames[0].persons[0].track_id == 1


def test_stitcher_continues_nearby_lost_track_only():
    st = OnlineTrackStitcher(max_gap_sec=1.0, max_dist_heights=1.5)
    assert st.update(0.0, [(1, (100, 100, 160, 300)), (2, (500, 100, 560, 300))]) == [1, 2]
    # id 1 is lost; new id 7 appears near it, id 2 still present.
    assert st.update(0.2, [(7, (90, 250, 250, 310)), (2, (500, 100, 560, 300))]) == [1, 2]
    assert st.update(0.3, [(7, (90, 250, 250, 310))]) == [1]
    # A new id far from every lost track keeps its own id.
    assert st.update(0.4, [(9, (0, 0, 30, 40))]) == [9]
    # Too late to continue anything.
    assert st.update(5.0, [(11, (90, 250, 250, 310))]) == [11]


def test_replay_emits_every_person_and_stitches_fragments():
    seq = _fall_with_bystander(40, fragment_at=24)
    raw = observations_from_cached_sequence(seq, "cam2")
    assert {o.track_id for o in raw} == {1, 2, 3}
    assert len(raw) == 80
    stitched = observations_from_cached_sequence(seq, "cam2", stitch_tracks=True)
    assert {o.track_id for o in stitched} == {1, 2}


def test_training_labels_only_the_falling_track(tmp_path: Path):
    save_keypoint_cache(_fall_with_bystander(60, fragment_at=24), tmp_path / "f.npz")
    record = {
        "sequence_id": "f",
        "source_dataset": "UP-Fall",
        "subject_id": "s1",
        "camera_id": "cam2",
        "is_fall": True,
        "fall_start_sec": 1.0,
        "fall_end_sec": 2.0,
        "lying_start_sec": 2.1,
    }
    # Without stitching the subject is split and no single track spans the fall.
    assert select_subject_track(load_track_arrays(tmp_path / "f.npz"), record) is None
    tracks = load_track_arrays(tmp_path / "f.npz", stitch_tracks=True)
    assert select_subject_track(tracks, record) == 1

    samples = load_dataset_samples_from_cache(
        [record], tmp_path, feature_set="v2", stitch_tracks=True
    )
    by_track: dict[str, set[int]] = {}
    for smp in samples:
        by_track.setdefault(smp.sample_id.split("_")[1], set()).add(smp.label_3class)
    assert by_track["t2"] == {0}  # bystander windows are negatives
    assert by_track["t1"] & {1, 2}  # subject windows carry fall labels
