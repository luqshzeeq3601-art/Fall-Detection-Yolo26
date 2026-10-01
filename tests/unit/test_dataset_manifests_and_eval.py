"""Unit tests for dataset manifest parser, validation, and evaluation metrics (P4-005)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eldercare.fall_engine.evaluation.manifest import (
    SequenceManifestRecord,
    load_manifest,
    validate_manifest_integrity,
)
from eldercare.fall_engine.evaluation.metrics import (
    EvaluationMetrics,
    compute_metrics,
)


@pytest.fixture
def manifests_dir() -> Path:
    """Return path to datasets/manifests directory."""
    manifest_dir = Path(__file__).resolve().parent.parent.parent / "datasets" / "manifests"
    assert manifest_dir.exists(), f"Manifest directory {manifest_dir} does not exist"
    return manifest_dir


def test_load_urfd_manifest_valid(manifests_dir: Path) -> None:
    """URFD manifest loads 70 sequences with strict 42 dev / 28 test split without leakage."""
    manifest_path = manifests_dir / "urfd_manifest.csv"
    records = load_manifest(manifest_path)

    assert len(records) == 70
    dev_records = [r for r in records if r.split == "dev"]
    test_records = [r for r in records if r.split == "test"]
    assert len(dev_records) == 42
    assert len(test_records) == 28

    fall_records = [r for r in records if r.is_fall]
    adl_records = [r for r in records if not r.is_fall]
    assert len(fall_records) == 30
    assert len(adl_records) == 40

    # Ensure all licenses are CC-BY-NC-SA-4.0
    assert all(r.license == "CC-BY-NC-SA-4.0" for r in records)


def test_load_upfall_manifest_valid(manifests_dir: Path) -> None:
    """UP-Fall manifest loads and validates subject-disjoint split."""
    manifest_path = manifests_dir / "upfall_manifest.csv"
    records = load_manifest(manifest_path)

    assert len(records) > 0
    dev_subjects = {r.subject_id for r in records if r.split == "dev"}
    test_subjects = {r.subject_id for r in records if r.split == "test"}

    # Must be strictly subject-disjoint
    assert len(dev_subjects.intersection(test_subjects)) == 0


def test_load_local_manifest_valid(manifests_dir: Path) -> None:
    """Local manifest loads valid clips with dev and test splits."""
    manifest_path = manifests_dir / "local_manifest.csv"
    records = load_manifest(manifest_path)

    assert len(records) > 0
    assert any(r.split == "dev" for r in records)
    assert any(r.split == "test" for r in records)


def test_manifest_integrity_catches_leakage() -> None:
    """Validation raises ValueError if the same sequence_id appears in both dev and test."""
    leaky_records = [
        SequenceManifestRecord(
            sample_id="s1",
            source_dataset="TEST",
            sequence_id="seq-01",
            subject_id="subj-1",
            camera_id="cam1",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="test1.mp4",
            split="dev",
            license="MIT",
            notes="",
        ),
        SequenceManifestRecord(
            sample_id="s2",
            source_dataset="TEST",
            sequence_id="seq-01",  # Same sequence ID in test split!
            subject_id="subj-1",
            camera_id="cam2",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="test2.mp4",
            split="test",
            license="MIT",
            notes="",
        ),
    ]

    with pytest.raises(ValueError, match="Data leakage detected"):
        validate_manifest_integrity(leaky_records)


def test_manifest_integrity_catches_duplicate_sample_id() -> None:
    """Validation raises ValueError if duplicate sample_ids exist."""
    dup_records = [
        SequenceManifestRecord(
            sample_id="s1",
            source_dataset="TEST",
            sequence_id="seq-01",
            subject_id="subj-1",
            camera_id="cam1",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="test1.mp4",
            split="dev",
            license="MIT",
            notes="",
        ),
        SequenceManifestRecord(
            sample_id="s1",  # Duplicate sample ID
            source_dataset="TEST",
            sequence_id="seq-02",
            subject_id="subj-2",
            camera_id="cam1",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="test2.mp4",
            split="dev",
            license="MIT",
            notes="",
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate sample_id"):
        validate_manifest_integrity(dup_records)


def test_compute_metrics_perfect_scores() -> None:
    """100% precision and recall when zero false positives and zero false negatives."""
    m = compute_metrics(tp=10, fp=0, tn=10, fn=0, alert_times=[1.2, 1.4, 1.3])
    assert isinstance(m, EvaluationMetrics)
    assert m.total_sequences == 20
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.accuracy == 1.0
    assert m.mean_time_to_alert_sec == 1.3


def test_compute_metrics_partial_scores() -> None:
    """Compute balanced precision, recall, F1."""
    # TP=8, FP=2 (Precision = 8/10 = 0.8), FN=2 (Recall = 8/10 = 0.8) -> F1 = 0.8
    m = compute_metrics(tp=8, fp=2, tn=8, fn=2)
    assert m.precision == 0.8
    assert m.recall == 0.8
    assert m.f1 == 0.8
    assert m.accuracy == 0.8


def test_compute_metrics_zero_denominators_safe() -> None:
    """Gracefully handles zero-division boundary cases without exception."""
    m = compute_metrics(tp=0, fp=0, tn=0, fn=0)
    assert m.total_sequences == 0
    assert m.accuracy == 0.0
    assert m.f1 == 0.0


def test_framework_freedom_ast_scan() -> None:
    """Verify evaluation subpackage modules do not import forbidden frameworks."""
    import eldercare.fall_engine.evaluation as eval_pkg
    import eldercare.fall_engine.evaluation.manifest as man_mod
    import eldercare.fall_engine.evaluation.metrics as met_mod
    import eldercare.fall_engine.evaluation.runner as run_mod

    modules = [eval_pkg, man_mod, met_mod, run_mod]
    forbidden_roots = ["cv2", "torch", "ultralytics", "torchvision"]

    for mod in modules:
        mod_path = Path(mod.__file__)
        tree = ast.parse(mod_path.read_text(encoding="utf-8"), filename=str(mod_path))
        imported_roots: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.append(node.module.split(".")[0])

        for forbidden in forbidden_roots:
            assert forbidden not in imported_roots, f"Module {mod.__name__} imports {forbidden}"
