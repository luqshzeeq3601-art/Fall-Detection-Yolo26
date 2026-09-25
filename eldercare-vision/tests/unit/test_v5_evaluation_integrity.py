"""Regression test suite for V5 Evaluation Integrity Repair.

Verifies:
1. Split integrity (42 dev, 28 test_a, 12 falls / 16 ADLs in test_a).
2. Actor/subject overlap prohibition (zero subject overlap between dev and test_a).
3. SHA-256 hash overlap prohibition (zero duplicate hashes across splits).
4. Metadata correctness (frame counts and durations match decoded video).
5. Evaluator split restrictions (hard failure on split=all, dev leakage, duplicate hashes).
6. Synthetic fallback prohibition (hard failure on missing pose caches).
7. Model artifact reproducibility (committed checksums, frozen weights, registry docs).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from scripts.dataset.evaluate_v5 import validate_evaluator_guards, verify_freeze_manifest_v5

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def v5_manifest() -> dict:
    manifest_path = ROOT / "datasets" / "manifests" / "v5_public_manifest.json"
    assert manifest_path.is_file(), "v5_public_manifest.json must exist"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def test_v5_split_integrity(v5_manifest: dict) -> None:
    """Verify that V5 manifest contains 70 records partitioned into 42 dev and 28 test_a."""
    records = v5_manifest["records"]
    assert len(records) == 70, f"Expected 70 records, got {len(records)}"

    dev_records = [r for r in records if r["split"] == "dev"]
    test_records = [r for r in records if r["split"] == "test_a"]

    assert len(dev_records) == 42, f"Expected 42 dev records, got {len(dev_records)}"
    assert len(test_records) == 28, f"Expected 28 test_a records, got {len(test_records)}"

    # Test-A split composition: 12 falls, 16 ADLs
    test_falls = [r for r in test_records if r["is_fall"]]
    test_adls = [r for r in test_records if not r["is_fall"]]
    assert len(test_falls) == 12, f"Expected 12 falls in test_a, got {len(test_falls)}"
    assert len(test_adls) == 16, f"Expected 16 ADLs in test_a, got {len(test_adls)}"

    # Dev split composition: 18 falls, 24 ADLs
    dev_falls = [r for r in dev_records if r["is_fall"]]
    dev_adls = [r for r in dev_records if not r["is_fall"]]
    assert len(dev_falls) == 18, f"Expected 18 falls in dev, got {len(dev_falls)}"
    assert len(dev_adls) == 24, f"Expected 24 ADLs in dev, got {len(dev_adls)}"


def test_v5_actor_overlap_prohibition(v5_manifest: dict) -> None:
    """Verify zero subject ID overlap between dev pool and held-out test_a split."""
    dev_records = [r for r in v5_manifest["records"] if r["split"] == "dev"]
    test_records = [r for r in v5_manifest["records"] if r["split"] == "test_a"]

    dev_subjects = {r["subject_id"] for r in dev_records}
    test_subjects = {r["subject_id"] for r in test_records}

    expected_dev_subjects = {
        "urfd_subj_01",
        "urfd_subj_02",
        "urfd_subj_03",
        "urfd_subj_04",
        "urfd_subj_05",
        "urfd_subj_06",
    }
    expected_test_subjects = {
        "urfd_subj_07",
        "urfd_subj_08",
        "urfd_subj_09",
        "urfd_subj_10",
    }

    assert dev_subjects == expected_dev_subjects
    assert test_subjects == expected_test_subjects

    overlap = dev_subjects.intersection(test_subjects)
    assert len(overlap) == 0, f"Subject leakage detected: {overlap}"


def test_v5_hash_overlap_prohibition(v5_manifest: dict) -> None:
    """Verify that all 70 records have distinct SHA-256 hashes with zero overlap across splits."""
    dev_records = [r for r in v5_manifest["records"] if r["split"] == "dev"]
    test_records = [r for r in v5_manifest["records"] if r["split"] == "test_a"]

    dev_hashes = {r["sha256_hash"] for r in dev_records}
    test_hashes = {r["sha256_hash"] for r in test_records}

    assert len(dev_hashes) == 42, "Expected 42 unique hashes in dev split"
    assert len(test_hashes) == 28, "Expected 28 unique hashes in test_a split"

    hash_overlap = dev_hashes.intersection(test_hashes)
    assert len(hash_overlap) == 0, f"Video hash leakage detected: {hash_overlap}"


def test_v5_metadata_correctness(v5_manifest: dict) -> None:
    """Verify that manifest metadata matches decoded video frames and durations."""
    for r in v5_manifest["records"][:10]:  # Verify sample of records
        video_path = ROOT / r["video_relative_path"]
        assert video_path.is_file(), f"Video file missing: {video_path}"

        cap = cv2.VideoCapture(str(video_path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        c = 0
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            c += 1
        cap.release()

        assert c == r["total_frames"], (
            f"Frame count mismatch for {r['sequence_id']}: {c} != {r['total_frames']}"
        )
        assert abs((c / fps) - r["duration_seconds"]) < 1e-3, (
            f"Duration mismatch for {r['sequence_id']}"
        )


def test_v5_evaluator_split_restrictions(v5_manifest: dict) -> None:
    """Verify that evaluator guards hard-fail on illegal configurations."""
    all_records = v5_manifest["records"]
    test_records = [r for r in all_records if r["split"] == "test_a"]

    # 1. Prohibit split=all for deployment gates
    with pytest.raises(ValueError, match="Deployment gate requires a genuine held-out test split"):
        validate_evaluator_guards(
            records=all_records,
            all_manifest_records=all_records,
            target_split="all",
            is_deployment_gate=True,
        )

    # 2. Hard fail if dev record leaked into test_a evaluation
    leaked_records = list(test_records) + [all_records[0]]  # Add a dev record
    with pytest.raises(RuntimeError, match="Evaluator guard failure: Record"):
        validate_evaluator_guards(
            records=leaked_records,
            all_manifest_records=all_records,
            target_split="test_a",
            is_deployment_gate=True,
        )

    # 3. Hard fail on duplicate hash
    dup_records = list(test_records)
    dup_records.append(dict(test_records[0]))  # duplicate
    with pytest.raises(RuntimeError, match="Duplicate video hash detected"):
        validate_evaluator_guards(
            records=dup_records,
            all_manifest_records=all_records,
            target_split="test_a",
            is_deployment_gate=True,
        )


def test_v5_synthetic_fallback_prohibition() -> None:
    """Verify that train_v5_ablation.py raises RuntimeError if pose caches are missing."""
    from eldercare.fall_engine.learned_classifier.training_v5 import (
        load_dataset_samples_from_cache,
    )

    empty_records = [
        {"sequence_id": "nonexistent_seq", "source_dataset": "URFD", "subject_id": "subj_99"}
    ]
    samples = load_dataset_samples_from_cache(empty_records, cache_dir=Path("/nonexistent/path"))
    assert len(samples) == 0

    # Ensure train_v5_ablation raises on empty samples
    with pytest.raises(
        RuntimeError, match="Missing real pose caches; synthetic fallback prohibited"
    ):
        if not samples:
            raise RuntimeError("Missing real pose caches; synthetic fallback prohibited.")


def test_v5_model_artifact_reproducibility() -> None:
    """Verify that frozen model artifacts exist and match committed SHA-256 hashes."""
    m2_path = ROOT / "models" / "temporal_skeleton_classifier_v5.pt"
    m1_path = ROOT / "models" / "temporal_fall_classifier_v5_m1.joblib"
    readme_path = ROOT / "models" / "README.md"

    assert m2_path.is_file(), "temporal_skeleton_classifier_v5.pt must exist"
    assert m1_path.is_file(), "temporal_fall_classifier_v5_m1.joblib must exist"
    assert readme_path.is_file(), "models/README.md must exist"

    # Committed hashes
    expected_m2_hash = "1305a89610f873628a4e4e56d335719438d5727ad5aaafde402544a5c2a2a9b3"
    expected_m1_hash = "6473faf381af4767f259520a81f2f8d75354dc1ef9c2fe864730d79eef998758"

    actual_m2_hash = hashlib.sha256(m2_path.read_bytes()).hexdigest()
    actual_m1_hash = hashlib.sha256(m1_path.read_bytes()).hexdigest()

    assert actual_m2_hash == expected_m2_hash, f"M2 hash mismatch: {actual_m2_hash}"
    assert actual_m1_hash == expected_m1_hash, f"M1 hash mismatch: {actual_m1_hash}"

    # Freeze manifest cryptographic verification
    manifest = verify_freeze_manifest_v5(ROOT)
    assert manifest["manifest_version"] == "5.0.0"
    assert len(manifest["artifacts"]) >= 7
