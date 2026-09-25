"""Unit tests for V4 Annotation & QA Verification Framework (P11.7-007)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eldercare.fall_engine.dataset.qa import (
    AnnotationQAVerifier,
    DatasetQAAuditResult,
    PoseGeometryAudit,
    TemporalIntervalAudit,
)
from eldercare.vision.pose.adapter import Keypoint, PersonPose

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def qa_verifier() -> AnnotationQAVerifier:
    return AnnotationQAVerifier()


def test_temporal_validation_valid_fall(qa_verifier: AnnotationQAVerifier):
    """Verify temporal validation passes on a well-formed fall record."""
    rec = {
        "sequence_id": "fall-01",
        "is_fall": True,
        "frame_count": 160,
        "fps": 30.0,
        "fall_start_frame": 83,
        "fall_end_frame": 112,
        "lying_start_frame": 113,
    }
    audit: TemporalIntervalAudit = qa_verifier.validate_temporal_sequence(rec)
    assert audit.is_valid is True
    assert audit.fall_duration_frames == 30
    assert audit.fall_duration_seconds == pytest.approx(1.0, rel=1e-2)
    assert audit.lying_duration_frames == 48
    assert audit.lying_duration_seconds == pytest.approx(1.6, rel=1e-2)
    assert len(audit.defects) == 0


def test_temporal_validation_invalid_fall_boundaries(qa_verifier: AnnotationQAVerifier):
    """Verify temporal validation catches inverted or out-of-bounds intervals."""
    # Inverted fall interval: end < start
    rec1 = {
        "sequence_id": "fall-bad-1",
        "is_fall": True,
        "frame_count": 100,
        "fps": 30.0,
        "fall_start_frame": 50,
        "fall_end_frame": 40,
        "lying_start_frame": 60,
    }
    audit1 = qa_verifier.validate_temporal_sequence(rec1)
    assert audit1.is_valid is False
    assert any("fall_end_frame" in d for d in audit1.defects)

    # Inverted lying interval: lying < fall_end
    rec2 = {
        "sequence_id": "fall-bad-2",
        "is_fall": True,
        "frame_count": 100,
        "fps": 30.0,
        "fall_start_frame": 30,
        "fall_end_frame": 50,
        "lying_start_frame": 45,
    }
    audit2 = qa_verifier.validate_temporal_sequence(rec2)
    assert audit2.is_valid is False
    assert any("lying_start_frame" in d for d in audit2.defects)

    # Lying starts beyond frame count
    rec3 = {
        "sequence_id": "fall-bad-3",
        "is_fall": True,
        "frame_count": 100,
        "fps": 30.0,
        "fall_start_frame": 30,
        "fall_end_frame": 50,
        "lying_start_frame": 105,
    }
    audit3 = qa_verifier.validate_temporal_sequence(rec3)
    assert audit3.is_valid is False
    assert any("exceeds frame_count" in d for d in audit3.defects)


def test_temporal_validation_valid_adl(qa_verifier: AnnotationQAVerifier):
    """Verify temporal validation passes on clean ADL record with no fall intervals."""
    rec = {
        "sequence_id": "adl-01",
        "is_fall": False,
        "frame_count": 150,
        "fps": 30.0,
        "fall_start_frame": None,
        "fall_end_frame": None,
        "lying_start_frame": None,
    }
    audit = qa_verifier.validate_temporal_sequence(rec)
    assert audit.is_valid is True
    assert len(audit.defects) == 0


def test_temporal_validation_leaked_adl(qa_verifier: AnnotationQAVerifier):
    """Verify temporal validation catches accidental fall interval in ADL record."""
    rec = {
        "sequence_id": "adl-leaked",
        "is_fall": False,
        "frame_count": 150,
        "fps": 30.0,
        "fall_start_frame": 20,
        "fall_end_frame": None,
        "lying_start_frame": None,
    }
    audit = qa_verifier.validate_temporal_sequence(rec)
    assert audit.is_valid is False
    assert any("contains non-null fall_start_frame" in d for d in audit.defects)


def test_pose_geometry_valid(qa_verifier: AnnotationQAVerifier):
    """Verify pose geometry audit passes on valid anatomical human pose."""
    # Build 17 keypoints with realistic positions
    kpts = []
    for i in range(17):
        kpts.append(Keypoint(x=100.0 + i, y=100.0 + i * 5, confidence=0.85, present=True))

    # Shoulders at y=120, hips at y=180
    kpts[5] = Keypoint(x=90.0, y=120.0, confidence=0.9, present=True)
    kpts[6] = Keypoint(x=110.0, y=120.0, confidence=0.9, present=True)
    kpts[11] = Keypoint(x=95.0, y=180.0, confidence=0.9, present=True)
    kpts[12] = Keypoint(x=105.0, y=180.0, confidence=0.9, present=True)

    pose = PersonPose(
        bbox_xyxy=(70.0, 80.0, 130.0, 240.0),
        detection_confidence=0.92,
        keypoints=tuple(kpts),
    )

    audit: PoseGeometryAudit = qa_verifier.validate_pose_geometry(pose, 640, 480)
    assert audit.is_valid is True
    assert audit.bbox_valid is True
    assert audit.torso_length_pixels == pytest.approx(60.0, rel=1e-1)
    assert audit.present_keypoint_count == 17
    assert len(audit.defects) == 0


def test_pose_geometry_degenerate_bbox(qa_verifier: AnnotationQAVerifier):
    """Verify pose geometry audit detects negative or collapsed bounding boxes."""
    kpts = tuple(Keypoint(x=50.0, y=50.0, confidence=0.8, present=True) for _ in range(17))
    pose = PersonPose(
        bbox_xyxy=(100.0, 100.0, 100.0, 100.0),  # width=0, height=0
        detection_confidence=0.5,
        keypoints=kpts,
    )
    audit = qa_verifier.validate_pose_geometry(pose, 640, 480)
    assert audit.is_valid is False
    assert audit.bbox_valid is False
    assert any("Degenerate bounding box" in d for d in audit.defects)


def test_pose_geometry_collapsed_torso(qa_verifier: AnnotationQAVerifier):
    """Verify pose geometry audit detects collapsed torso length."""
    kpts = []
    for _ in range(17):
        kpts.append(Keypoint(x=100.0, y=100.0, confidence=0.8, present=True))

    # Place shoulders and hips at the exact same point
    kpts[5] = Keypoint(x=100.0, y=100.0, confidence=0.9, present=True)
    kpts[6] = Keypoint(x=100.0, y=100.0, confidence=0.9, present=True)
    kpts[11] = Keypoint(x=100.0, y=100.0, confidence=0.9, present=True)
    kpts[12] = Keypoint(x=100.0, y=100.0, confidence=0.9, present=True)

    pose = PersonPose(
        bbox_xyxy=(80.0, 80.0, 120.0, 120.0),
        detection_confidence=0.8,
        keypoints=tuple(kpts),
    )
    audit = qa_verifier.validate_pose_geometry(pose, 640, 480)
    assert audit.is_valid is False
    assert any("Collapsed torso" in d for d in audit.defects)


def test_full_manifest_qa_audit(qa_verifier: AnnotationQAVerifier):
    """Verify full QA audit over the master V4 manifest passes with 0 defects."""
    manifest_path = ROOT / "datasets" / "manifests" / "v4_multi_source_manifest.json"
    assert manifest_path.is_file(), f"Missing {manifest_path}"

    res: DatasetQAAuditResult = qa_verifier.audit_manifest(manifest_path)
    assert res.overall_qa_status == "PASS"
    assert res.total_sequences == 70
    assert res.fall_sequences == 30
    assert res.adl_sequences == 40
    assert res.valid_sequences == 70
    assert res.defective_sequences == 0
    assert res.temporal_compliance_rate == 1.0
    assert len(res.defects) == 0


def test_qa_audit_report_exists():
    """Verify that the QA audit report exists and records 100% compliance."""
    report_file = ROOT / "docs" / "reports" / "P11.7-007-annotation-qa-report.md"
    assert report_file.is_file(), f"Missing {report_file}"

    text = report_file.read_text(encoding="utf-8")
    assert "Overall Status:** **PASS**" in text
    assert "Temporal Compliance Rate:** 100.0%" in text
    assert "No defects detected across 70 sequences" in text
