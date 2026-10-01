# ruff: noqa: E501
"""Unit and Integration Tests for Unified End-to-End V4 Pipeline & Freeze Manifest (P11.7-014)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from eldercare.fall_engine.pipeline_v4 import FallEnginePipelineV4
from eldercare.fall_engine.state_machine.states import FallState
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation
from tests.local_artifacts import requires_local


def _make_obs(
    track_id: int,
    t: float,
    cx: float = 320.0,
    cy: float = 240.0,
    w: float = 100.0,
    h: float = 200.0,
    angle_deg: float = 85.0,
    ankle_y: float | None = None,
) -> TrackObservation:
    rad = np.radians(angle_deg)
    half_h = h / 2.0
    dx = half_h * np.cos(rad)
    dy = half_h * np.sin(rad)

    shoulder_x = cx + dx * 0.4
    shoulder_y = cy - dy * 0.4
    hip_x = cx - dx * 0.2
    hip_y = cy + dy * 0.2
    head_x = cx + dx * 0.8
    head_y = cy - dy * 0.8
    actual_ankle_y = ankle_y if ankle_y is not None else (cy + half_h * 0.9)

    kpts = []
    kpts.append(Keypoint(present=True, x=head_x, y=head_y, confidence=0.9))
    for _ in range(4):
        kpts.append(Keypoint(present=True, x=head_x, y=head_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x - 20, y=shoulder_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=shoulder_x + 20, y=shoulder_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=shoulder_x - 25, y=shoulder_y + 30, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x + 25, y=shoulder_y + 30, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x - 25, y=shoulder_y + 60, confidence=0.9))
    kpts.append(Keypoint(present=True, x=shoulder_x + 25, y=shoulder_y + 60, confidence=0.9))
    kpts.append(Keypoint(present=True, x=hip_x - 15, y=hip_y, confidence=0.95))
    kpts.append(Keypoint(present=True, x=hip_x + 15, y=hip_y, confidence=0.95))
    knee_y = (hip_y + actual_ankle_y) / 2.0
    kpts.append(Keypoint(present=True, x=hip_x - 15, y=knee_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=hip_x + 15, y=knee_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx - 15, y=actual_ankle_y, confidence=0.9))
    kpts.append(Keypoint(present=True, x=cx + 15, y=actual_ankle_y, confidence=0.9))

    return TrackObservation(
        camera_id="cam_e2e",
        track_id=track_id,
        timestamp=float(t),
        bbox_xyxy=(cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0),
        detection_confidence=0.95,
        keypoints=tuple(kpts),
        image_width=640,
        image_height=480,
    )


def test_pipeline_v4_initialization_defaults():
    """Verify default instantiation of FallEnginePipelineV4."""
    pipeline = FallEnginePipelineV4()
    assert pipeline.camera_normalizer is not None
    assert pipeline.adl_suppressor is not None
    assert pipeline.cooldown_manager is not None
    assert pipeline.classifier is not None


def test_pipeline_v4_standing_track_processing():
    """Verify standing tracks stay in NORMAL state without emitting events."""
    pipeline = FallEnginePipelineV4()

    for i in range(30):
        obs = _make_obs(track_id=1, t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0)
        state, event = pipeline.process_observation(obs)
        assert state == FallState.NORMAL
        assert event is None


def test_pipeline_v4_adl_suppression_e2e():
    """Verify controlled bending is suppressed end-to-end without emitting false alert."""
    pipeline = FallEnginePipelineV4()

    # Standing
    for i in range(30):
        obs = _make_obs(track_id=1, t=i * 0.0333, cy=100.0, h=200.0, angle_deg=85.0, ankle_y=300.0)
        pipeline.process_observation(obs)

    # Smooth bending forward
    for i in range(1, 20):
        t = 1.0 + i * 0.0333
        frac = min(1.0, i / 15.0)
        obs = _make_obs(
            track_id=1,
            t=t,
            cy=100.0 + 40.0 * frac,
            h=200.0 - 90.0 * frac,
            angle_deg=85.0 - 55.0 * frac,
            ankle_y=300.0,
        )
        state, event = pipeline.process_observation(obs)
        assert event is None


def test_pipeline_v4_multi_person_frame_processing():
    """Verify multi-person frame batch processing."""
    pipeline = FallEnginePipelineV4()

    obs_p1 = _make_obs(track_id=1, t=0.0, cx=200.0)
    obs_p2 = _make_obs(track_id=2, t=0.0, cx=450.0)

    frame_results = pipeline.process_frame_observations([obs_p1, obs_p2])
    assert len(frame_results) == 2
    assert frame_results[0][0] == 1
    assert frame_results[1][0] == 2
    assert frame_results[0][1] == FallState.NORMAL
    assert frame_results[1][1] == FallState.NORMAL


def test_pipeline_v4_track_reset_and_cleanup():
    """Verify track reset removes internal state machine and history."""
    pipeline = FallEnginePipelineV4()

    obs = _make_obs(track_id=5, t=0.0)
    pipeline.process_observation(obs)
    assert ("cam_e2e", 5) in pipeline._state_machines

    pipeline.reset_track("cam_e2e", 5)
    assert ("cam_e2e", 5) not in pipeline._state_machines


@requires_local("datasets/cache/v4_dev_augmented_features.npz")
def test_v4_freeze_manifest_integrity():
    """Verify that models/v4_freeze_manifest.json exists and all hashes match disk."""
    base_dir = Path(__file__).resolve().parents[2]
    manifest_path = base_dir / "models" / "v4_freeze_manifest.json"
    assert manifest_path.is_file(), "v4_freeze_manifest.json must exist"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "4.0.0"
    assert manifest["status"] == "FROZEN_FOR_TEST_EVALUATION"
    assert len(manifest["artifacts"]) >= 9

    for rel_path, meta in manifest["artifacts"].items():
        full_path = base_dir / rel_path
        assert full_path.is_file(), f"Frozen artifact {rel_path} does not exist"
        h = hashlib.sha256()
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        disk_hash = h.hexdigest()
        assert disk_hash == meta["sha256"], (
            f"Hash mismatch for {rel_path}: {disk_hash} != {meta['sha256']}"
        )
