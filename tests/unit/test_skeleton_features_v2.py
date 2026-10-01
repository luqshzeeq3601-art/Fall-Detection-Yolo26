"""Tests for the V6.2 view-robust skeleton feature set (v2).

Verifies:
1. v2 window features expose descent (hip trajectory / velocity) and body shortening.
2. Training (cache arrays) and inference (TrackObservation history) produce identical
   v2 tensors for the same frames (no train/serve skew).
3. Saved models round-trip their feature set; v1 remains the default.
4. v2 augmentation negates the horizontal trajectory channel on flip.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    FEATURE_SET_DIMS,
    TemporalSkeletonClassifierV5,
    TemporalSkeletonNetV5,
    extract_skeleton_sequence_tensor,
    skeleton_features_v2,
)
from eldercare.fall_engine.learned_classifier.training_v5 import (
    augment_batch_tensors,
    load_dataset_samples_from_cache,
    skeleton_config_for,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

# Standing COCO-17 skeleton (pixels), roughly 200 px tall, hips at y=300.
_STAND = np.array(
    [
        [320, 130],
        [315, 125],
        [325, 125],
        [310, 128],
        [330, 128],
        [300, 170],
        [340, 170],
        [295, 220],
        [345, 220],
        [292, 265],
        [348, 265],
        [305, 300],
        [335, 300],
        [305, 350],
        [335, 350],
        [305, 400],
        [335, 400],
    ],
    dtype=np.float64,
)


def _falling_sequence(t_len: int = 40) -> tuple[np.ndarray, ...]:
    """Skeleton that drops and flattens vertically over time (fall toward camera)."""
    kpts = np.zeros((t_len, 17, 3))
    bboxes = np.zeros((t_len, 4))
    for t in range(t_len):
        prog = min(1.0, max(0.0, (t - 10) / 15.0))
        squash = 1.0 - 0.7 * prog
        drop = 120.0 * prog
        xy = _STAND.copy()
        xy[:, 1] = 300.0 + (xy[:, 1] - 300.0) * squash + drop
        kpts[t, :, :2] = xy
        kpts[t, :, 2] = 0.9
        bboxes[t] = [xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()]
    kpts[5:8, 3, :2] = np.nan  # a few missing keypoints
    ts = np.arange(t_len) / 15.0
    return kpts, bboxes, ts, np.full(t_len, 480.0), np.full(t_len, 0.95)


def _observations(arrays: tuple[np.ndarray, ...]) -> list[TrackObservation]:
    kpts, bboxes, ts, img_h, confs = arrays
    obs = []
    for t in range(len(ts)):
        kps = tuple(
            Keypoint(x=None, y=None, confidence=float(kpts[t, i, 2]), present=False)
            if np.isnan(kpts[t, i, 0])
            else Keypoint(
                x=float(kpts[t, i, 0]),
                y=float(kpts[t, i, 1]),
                confidence=float(kpts[t, i, 2]),
                present=True,
            )
            for i in range(17)
        )
        obs.append(
            TrackObservation(
                camera_id="cam2",
                track_id=1,
                timestamp=float(ts[t]),
                bbox_xyxy=tuple(float(v) for v in bboxes[t]),
                detection_confidence=float(confs[t]),
                keypoints=kps,
                image_width=640,
                image_height=int(img_h[t]),
            )
        )
    return obs


def test_v2_features_expose_descent_and_shortening():
    arrays = _falling_sequence()
    feats = skeleton_features_v2(*(a[5:35] for a in arrays))
    assert feats.shape == (30, FEATURE_SET_DIMS["v2"])
    hip_dy, hip_vy, head_above_hip, bbox_ratio = (
        feats[:, 72],
        feats[:, 74],
        feats[:, 75],
        feats[:, 76],
    )
    assert hip_dy[0] == pytest.approx(0.0)
    assert hip_dy[-1] > 0.8  # 120 px drop vs ~130 px reference torso
    assert hip_vy[10:20].mean() > 0.5  # downward velocity during the fall
    assert head_above_hip[-1] < head_above_hip[0] * 0.5  # body flattens
    assert bbox_ratio[-1] < 0.5
    assert np.isfinite(feats).all()


def test_v2_training_and_inference_features_match(tmp_path: Path):
    arrays = _falling_sequence()
    kpts, bboxes, ts, img_h, confs = arrays
    np.savez(
        tmp_path / "seq_a.npz",
        keypoints=kpts.astype(np.float32),
        bboxes=bboxes.astype(np.float32),
        timestamps=ts,
        dims=np.tile([640, 480], (len(ts), 1)),
        confidences=confs.astype(np.float32),
    )
    record = {
        "sequence_id": "seq_a",
        "source_dataset": "UP-Fall",
        "subject_id": "s1",
        "camera_id": "cam2",
        "is_fall": True,
        "fall_start_sec": 0.7,
        "fall_end_sec": 1.7,
        "lying_start_sec": 1.8,
    }
    samples = load_dataset_samples_from_cache([record], tmp_path, feature_set="v2")
    assert samples and samples[0].camera_id == "cam2"
    assert samples[0].skeleton_tensor.shape == (30, FEATURE_SET_DIMS["v2"])

    # Inference path on the same frames, round-tripped through float32 like the cache.
    obs = _observations(
        (
            kpts.astype(np.float32).astype(np.float64),
            bboxes.astype(np.float32).astype(np.float64),
            ts,
            img_h,
            confs.astype(np.float32).astype(np.float64),
        )
    )
    served = extract_skeleton_sequence_tensor(obs[0:30], 30, feature_set="v2")
    np.testing.assert_allclose(samples[0].skeleton_tensor, served, atol=1e-4)

    # Short histories are left-padded identically to short cached sequences.
    short = extract_skeleton_sequence_tensor(obs[0:12], 30, feature_set="v2")
    assert short.shape == (30, FEATURE_SET_DIMS["v2"])
    np.testing.assert_allclose(short[:18, 72], 0.0)


def test_model_roundtrip_keeps_feature_set(tmp_path: Path):
    cfg = skeleton_config_for("v2")
    clf = TemporalSkeletonClassifierV5(
        model=TemporalSkeletonNetV5(in_features=cfg.total_feature_dim), config=cfg
    )
    clf.save(tmp_path / "m.pt")
    loaded = TemporalSkeletonClassifierV5.load(tmp_path / "m.pt")
    assert loaded.config.feature_set == "v2"
    probs = loaded.predict_probabilities(_observations(_falling_sequence())[:30])
    assert sum(probs) == pytest.approx(1.0, abs=1e-5)
    assert TemporalSkeletonClassifierV5().config.feature_set == "v1"


def test_v2_augmentation_flips_horizontal_trajectory():
    torch.manual_seed(0)
    x = torch.zeros(64, 30, FEATURE_SET_DIMS["v2"])
    x[:, :, 73] = 1.0  # hip_dx_from_start
    aug = augment_batch_tensors(x, feature_set="v2")
    values = set(aug[:, 0, 73].tolist())
    assert values == {1.0, -1.0}
