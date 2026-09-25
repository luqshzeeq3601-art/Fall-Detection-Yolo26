"""Unit tests for V4 Dataset Acquisition & Ingestion Protocol (P11.7-006)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eldercare.fall_engine.dataset.ingestion import (
    DatasetIngestionEngine,
    OpticalAuthenticityValidator,
)
from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
    SplitLeakageError,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def ingestion_engine(repo_root: Path) -> DatasetIngestionEngine:
    return DatasetIngestionEngine(repo_root=repo_root)


def test_optical_authenticity_validator_real_video(repo_root: Path):
    """Verify that genuine optical camera footage passes authenticity check."""
    real_video = repo_root / "datasets" / "raw" / "urfd" / "fall-01-cam0.mp4"
    assert real_video.is_file(), f"Missing real video: {real_video}"

    validator = OpticalAuthenticityValidator()
    score = validator.validate_video(real_video, sample_count=3)

    assert score.is_optical_capture is True
    assert score.authenticity_score > 0.5
    assert score.unique_color_count > 800
    assert score.laplacian_variance > 200.0
    assert score.rejection_reason is None


def test_optical_authenticity_validator_synthetic_detection(repo_root: Path):
    """Verify that flat OpenCV synthetic animations are detected and flagged."""
    synth_video = repo_root / "datasets" / "raw" / "upfall" / "s01_a01_t1.mp4"
    if not synth_video.is_file():
        pytest.skip("Synthetic UP-Fall video not found on disk")

    validator = OpticalAuthenticityValidator()
    score = validator.validate_video(synth_video, sample_count=3)

    assert score.is_optical_capture is False
    assert score.rejection_reason is not None
    assert "Synthetic/flat render detected" in score.rejection_reason


def test_urfd_ground_truth_parsing(ingestion_engine: DatasetIngestionEngine, repo_root: Path):
    """Verify parsing of ground-truth temporal intervals from urfall-cam0-falls.csv."""
    gt_csv = repo_root / "datasets" / "raw" / "urfd" / "urfall-cam0-falls.csv"
    assert gt_csv.is_file(), f"Missing ground truth CSV: {gt_csv}"

    intervals = ingestion_engine.parse_urfd_ground_truth(gt_csv)
    assert len(intervals) == 30, f"Expected 30 fall sequences in intervals, got {len(intervals)}"

    # Check known sequence: fall-01
    assert "fall-01" in intervals
    f_start, f_end, l_start = intervals["fall-01"]
    assert f_start == 83
    assert f_end == 112
    assert l_start == 113


def test_urfd_ingestion_integrity(ingestion_engine: DatasetIngestionEngine):
    """Verify that all 70 raw URFD videos are ingested with verified metadata."""
    records = ingestion_engine.ingest_urfd()
    assert len(records) == 70

    falls = [r for r in records if r.is_fall]
    adls = [r for r in records if not r.is_fall]
    assert len(falls) == 30
    assert len(adls) == 40

    for r in records:
        assert r.sha256 and len(r.sha256) == 64
        assert r.frame_count > 0
        assert r.fps > 0
        assert r.duration_seconds > 0
        assert r.width == 640
        assert r.height == 240
        assert r.license == "CC-BY-NC-SA-4.0"
        assert r.source_dataset == "URFD"
        assert r.deployment_evidence is True
        assert r.split in ("dev", "test")

        if r.is_fall:
            assert r.fall_start_frame is not None
            assert r.fall_end_frame is not None
            assert r.fall_start_frame <= r.fall_end_frame


def test_master_manifest_files_exist_and_match(repo_root: Path):
    """Verify that master V4 manifests exist and contain all 70 records."""
    json_path = repo_root / "datasets" / "manifests" / "v4_multi_source_manifest.json"
    csv_path = repo_root / "datasets" / "manifests" / "v4_multi_source_manifest.csv"

    assert json_path.is_file(), f"Missing {json_path}"
    assert csv_path.is_file(), f"Missing {csv_path}"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    assert len(records) == 70
    assert data["metadata"]["task"] == "P11.7-006"


def test_manifest_verification_on_disk(ingestion_engine: DatasetIngestionEngine, repo_root: Path):
    """Verify that every on-disk video matches the manifest cryptographic hash."""
    json_path = repo_root / "datasets" / "manifests" / "v4_multi_source_manifest.json"
    res = ingestion_engine.verify_manifest_integrity(json_path)

    assert res["status"] == "PASS"
    assert res["verified_records"] == 70
    assert res["total_records"] == 70


def test_split_isolation_and_subject_disjointness(repo_root: Path):
    """Verify zero subject overlap and zero hash overlap between dev and test."""
    guard = DatasetSplitGuard(repo_root)
    json_path = repo_root / "datasets" / "manifests" / "v4_multi_source_manifest.json"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    records = data["records"]

    res = guard.verify_partitions(records, train_split="dev", dev_split="dev", holdout_split="test")
    assert res["zero_subject_overlap"] is True
    assert res["zero_hash_overlap"] is True

    dev_subjs = set(r["subject_id"] for r in records if r["split"] == "dev")
    test_subjs = set(r["subject_id"] for r in records if r["split"] == "test")

    assert len(dev_subjs) == 6
    assert len(test_subjs) == 4
    assert dev_subjs.isdisjoint(test_subjs)


def test_training_isolation_guard(repo_root: Path):
    """Verify that training access to holdout split triggers HoldoutAccessError."""
    guard = DatasetSplitGuard(repo_root)

    # dev split allowed without raising error
    guard.enforce_training_isolation("dev")
    guard.enforce_training_isolation("train")

    # test and holdout blocked
    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
        guard.enforce_training_isolation("test")

    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
        guard.enforce_training_isolation("holdout")


def test_tamper_detection_raises_error(ingestion_engine: DatasetIngestionEngine, tmp_path: Path):
    """Verify that altered video hash in manifest triggers SplitLeakageError."""
    # Create fake manifest with bad hash
    fake_manifest = tmp_path / "tampered_manifest.json"
    fake_data = {
        "records": [
            {
                "sample_id": "test-tamper",
                "path_local": "datasets/raw/urfd/fall-01-cam0.mp4",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }
        ]
    }
    with open(fake_manifest, "w", encoding="utf-8") as f:
        json.dump(fake_data, f)

    with pytest.raises(SplitLeakageError, match="Manifest integrity verification failed"):
        ingestion_engine.verify_manifest_integrity(fake_manifest)
