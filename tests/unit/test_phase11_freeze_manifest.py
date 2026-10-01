"""Verification suite for Phase 11 Freeze Manifest and Anti-Leakage Invariants (P11-001)."""

from __future__ import annotations

import json
from pathlib import Path

from eldercare.fall_engine.calibration.freeze import (
    FROZEN_ARTIFACT_DIGESTS,
    compute_file_sha256,
)
from eldercare.fall_engine.evaluation.manifest import load_manifest
from tests.local_artifacts import requires_local


def test_freeze_manifest_exists_and_valid() -> None:
    manifest_path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / "reports"
        / "P11-001-freeze-manifest.json"
    )
    assert manifest_path.is_file(), f"Freeze manifest missing at {manifest_path}"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["phase"] == "Phase 11 — Final Evaluation"
    assert data["git"]["commit_sha"] == "58ecf401360c685fe6f02a7ec6d7842212ed0d12"
    assert data["hardware"]["gpu_name"] == "NVIDIA GeForce RTX 3070"
    assert data["models"]["production_runtime"] == "TensorRT 11 FP16"


@requires_local("yolo26s-pose.pt")
def test_model_artifact_digests_match() -> None:
    root = Path(__file__).resolve().parent.parent.parent

    pt_path = root / "yolo26s-pose.pt"
    assert pt_path.is_file()
    assert (
        compute_file_sha256(pt_path, normalize_newlines=False)
        == "a083adb42303728ae14c4bd6bd56d80da46f82fb2564dbd6f31dcc92ea321646"
    )

    onnx_path = root / "yolo26s-pose.onnx"
    assert onnx_path.is_file()
    assert (
        compute_file_sha256(onnx_path, normalize_newlines=False)
        == "6b55bd4962707609484aae62886c4ced5cb11e5015761ba5d587840a2a08ca45"
    )

    engine_path = root / "yolo26s-pose.engine"
    assert engine_path.is_file()
    assert (
        compute_file_sha256(engine_path, normalize_newlines=False)
        == "6cf6142e7d4301b386b286bdcccce31a1a393457ce01a0e8b13fc5234e89f947"
    )


def test_configuration_digests_match() -> None:
    root = Path(__file__).resolve().parent.parent.parent

    for rel_path, expected_hash in FROZEN_ARTIFACT_DIGESTS.items():
        full_path = root / rel_path
        assert full_path.is_file(), f"Artifact {rel_path} missing"
        actual_hash = compute_file_sha256(full_path, normalize_newlines=True)
        assert actual_hash == expected_hash, (
            f"Hash mismatch for {rel_path}: {actual_hash} != {expected_hash}"
        )


def test_split_anti_leakage_invariants() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    manifests_dir = root / "datasets" / "manifests"

    # URFD anti-leakage
    urfd_records = load_manifest(manifests_dir / "urfd_manifest.csv")
    urfd_dev = {r.sequence_id for r in urfd_records if r.split == "dev"}
    urfd_test = {r.sequence_id for r in urfd_records if r.split == "test"}
    assert len(urfd_dev) == 42
    assert len(urfd_test) == 28
    assert len(urfd_dev.intersection(urfd_test)) == 0

    # UP-Fall subject-disjoint anti-leakage
    upfall_records = load_manifest(manifests_dir / "upfall_manifest.csv")
    upfall_dev_subj = {r.subject_id for r in upfall_records if r.split == "dev"}
    upfall_test_subj = {r.subject_id for r in upfall_records if r.split == "test"}
    assert len(upfall_dev_subj) == 5
    assert len(upfall_test_subj) == 6
    assert len(upfall_dev_subj.intersection(upfall_test_subj)) == 0
    assert len(upfall_records) == 42
    assert len([r for r in upfall_records if r.split == "dev"]) == 27
    assert len([r for r in upfall_records if r.split == "test"]) == 15

    # Local anti-leakage
    local_records = load_manifest(manifests_dir / "local_manifest.csv")
    local_dev = {r.sequence_id for r in local_records if r.split == "dev"}
    local_test = {r.sequence_id for r in local_records if r.split == "test"}
    assert len(local_dev) == 7
    assert len(local_test) == 5
    assert len(local_dev.intersection(local_test)) == 0
