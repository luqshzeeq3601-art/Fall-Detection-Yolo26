"""P11.7-004: Unit tests for V4 data protocol, split integrity, and holdout isolation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
    SplitLeakageError,
)

ROOT = Path(__file__).resolve().parents[2]


def test_manifest_schema_validation() -> None:
    """Ensure manifest schema checks enforce required columns and valid splits."""
    guard = DatasetSplitGuard()

    # Valid CSV content
    valid_csv = (
        "sample_id,source_dataset,sequence_id,subject_id,camera_id,activity,is_fall,"
        "path_local,split,license\n"
        "s1,URFD,seq1,subj1,cam0,fall,1,raw/urfd/fall-01-cam0.mp4,dev,CC-BY-4.0\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(valid_csv)
        f_path = Path(f.name)

    try:
        rows = guard.load_and_validate_manifest(f_path)
        assert len(rows) == 1
        assert rows[0]["sample_id"] == "s1"
    finally:
        f_path.unlink(missing_ok=True)

    # Missing column test
    invalid_csv = "sample_id,sequence_id,subject_id\ns1,seq1,subj1\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(invalid_csv)
        f_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="missing required columns"):
            guard.load_and_validate_manifest(f_path)
    finally:
        f_path.unlink(missing_ok=True)


def test_subject_disjointness_enforcement() -> None:
    """Ensure overlapping subjects across splits raise SplitLeakageError."""
    guard = DatasetSplitGuard()

    # Disjoint partitions
    disjoint_records = [
        {"sample_id": "s1", "split": "train", "subject_id": "sub_A", "path_local": ""},
        {"sample_id": "s2", "split": "dev", "subject_id": "sub_B", "path_local": ""},
        {"sample_id": "s3", "split": "holdout", "subject_id": "sub_C", "path_local": ""},
    ]
    res = guard.verify_partitions(disjoint_records)
    assert res["zero_subject_overlap"] is True
    assert res["sample_counts"] == {"train": 1, "dev": 1, "holdout": 1}

    # Leaking subject across train and holdout
    leaking_records = [
        {"sample_id": "s1", "split": "train", "subject_id": "sub_A", "path_local": ""},
        {"sample_id": "s2", "split": "holdout", "subject_id": "sub_A", "path_local": ""},
    ]
    with pytest.raises(SplitLeakageError, match="CRITICAL DATA LEAKAGE: Overlapping subjects"):
        guard.verify_partitions(leaking_records)


def test_training_isolation_enforcement() -> None:
    """Verify that training routines cannot access holdout or test partitions."""
    guard = DatasetSplitGuard()

    # Allowed splits during training
    guard.enforce_training_isolation("train")
    guard.enforce_training_isolation("dev")

    # Forbidden splits during training
    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS: ModelTraining"):
        guard.enforce_training_isolation("holdout", context="ModelTraining")

    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS: ModelTraining"):
        guard.enforce_training_isolation("test", context="ModelTraining")


def test_real_urfd_manifest_partition_integrity() -> None:
    """Verify that the official URFD manifest has zero subject overlap between dev and test."""
    guard = DatasetSplitGuard()
    manifest_path = ROOT / "datasets" / "manifests" / "urfd_manifest.csv"
    assert manifest_path.is_file()

    records = guard.load_and_validate_manifest(manifest_path)
    res = guard.verify_partitions(records)

    assert res["zero_subject_overlap"] is True
    assert res["sample_counts"]["dev"] == 42
    assert res["sample_counts"]["test"] == 28
    assert res["subject_counts"]["dev"] == 6  # subj-01 through subj-06
    assert res["subject_counts"]["test"] == 4  # subj-07 through subj-10
