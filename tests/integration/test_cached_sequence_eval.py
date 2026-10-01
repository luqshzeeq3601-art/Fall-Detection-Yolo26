"""Integration tests for cached keypoint sequence evaluation pipeline (P4-006)."""

from __future__ import annotations

from pathlib import Path

from eldercare.fall_engine.cache import (
    KeypointCacheMetadata,
    load_keypoint_cache,
    save_keypoint_cache,
    sequence_from_observations,
    sequence_to_observations,
    validate_cache_provenance,
)
from eldercare.fall_engine.evaluation import (
    SequenceEvaluationRunner,
    SequenceManifestRecord,
)
from tests.fixtures.synthetic_fall_fixtures import (
    generate_fall_sequence,
    generate_walking_sequence,
)


def test_cached_sequence_evaluation_parity(tmp_path: Path) -> None:
    """Verify that cached evaluation produces identical metrics to live evaluation."""
    # 1. Generate live synthetic sequences
    fall_obs = generate_fall_sequence(fps=30.0, camera_id="cam_01")
    adl_obs = generate_walking_sequence(fps=30.0, camera_id="cam_01")

    # 2. Build metadata & cache structures
    fall_meta = KeypointCacheMetadata(
        source_sample_id="urfd_fall_01",
        model_name="yolo26s-pose.pt",
        inference_library_version="ultralytics==8.3.0",
        extraction_timestamp="2026-09-23T12:00:00Z",
        total_frames=len(fall_obs),
        inference_config={"imgsz": 640},
        fps=30.0,
    )
    adl_meta = KeypointCacheMetadata(
        source_sample_id="urfd_adl_01",
        model_name="yolo26s-pose.pt",
        inference_library_version="ultralytics==8.3.0",
        extraction_timestamp="2026-09-23T12:00:00Z",
        total_frames=len(adl_obs),
        inference_config={"imgsz": 640},
        fps=30.0,
    )

    fall_cached_seq = sequence_from_observations(fall_meta, fall_obs)
    adl_cached_seq = sequence_from_observations(adl_meta, adl_obs)

    # 3. Save to disk (fall as json, adl as compressed json.gz)
    fall_path = save_keypoint_cache(fall_cached_seq, tmp_path / "fall.json")
    adl_path = save_keypoint_cache(adl_cached_seq, tmp_path / "adl.json.gz", compress=True)

    # 4. Load back from disk
    loaded_fall_seq = load_keypoint_cache(fall_path)
    loaded_adl_seq = load_keypoint_cache(adl_path)

    assert validate_cache_provenance(loaded_fall_seq, expected_model="yolo26s-pose.pt") is True
    assert validate_cache_provenance(loaded_adl_seq, expected_model="yolo26s-pose.pt") is True

    # 5. Convert back to observation streams
    reconstructed_fall_obs = sequence_to_observations(loaded_fall_seq, camera_id="cam_01")
    reconstructed_adl_obs = sequence_to_observations(loaded_adl_seq, camera_id="cam_01")

    # 6. Run SequenceEvaluationRunner on both live and cached
    runner_live = SequenceEvaluationRunner()
    fall_record = SequenceManifestRecord(
        sample_id="fall_01",
        source_dataset="urfd",
        sequence_id="fall_01",
        subject_id="sub_01",
        camera_id="cam_01",
        activity="fall_floor",
        is_fall=True,
        fall_type="forward",
        path_local="data/fall_01",
        split="dev",
        license="CC-BY-4.0",
        notes="",
    )
    adl_record = SequenceManifestRecord(
        sample_id="adl_01",
        source_dataset="urfd",
        sequence_id="adl_01",
        subject_id="sub_01",
        camera_id="cam_01",
        activity="walking",
        is_fall=False,
        fall_type="none",
        path_local="data/adl_01",
        split="dev",
        license="CC-BY-4.0",
        notes="",
    )

    batch_live = [
        (fall_record, fall_obs, 1.0),
        (adl_record, adl_obs, None),
    ]
    metrics_live, results_live = runner_live.evaluate_batch(batch_live)

    runner_cached = SequenceEvaluationRunner()
    batch_cached = [
        (fall_record, reconstructed_fall_obs, 1.0),
        (adl_record, reconstructed_adl_obs, None),
    ]
    metrics_cached, results_cached = runner_cached.evaluate_batch(batch_cached)

    # 7. Assert complete parity
    assert metrics_cached.total_sequences == metrics_live.total_sequences == 2
    assert metrics_cached.tp == metrics_live.tp == 1
    assert metrics_cached.tn == metrics_live.tn == 1
    assert metrics_cached.fp == metrics_live.fp == 0
    assert metrics_cached.fn == metrics_live.fn == 0
    assert metrics_cached.precision == metrics_live.precision == 1.0
    assert metrics_cached.recall == metrics_live.recall == 1.0
    assert metrics_cached.f1 == metrics_live.f1 == 1.0
    assert len(results_cached) == len(results_live) == 2
