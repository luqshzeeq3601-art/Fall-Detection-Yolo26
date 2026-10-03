"""Phase 11.8 V5 Temporal Skeleton Normalization & Deep Sequence Classifier (P11.8-017..019).

Processes 15 Hz keypoint sequences with hip-centering, torso-length scale normalization,
and confidence masking. Feeds into a lightweight Temporal CNN-GRU architecture for
3-class temporal action recognition: Normal/ADL (0), Falling (1), Fallen/Lying (2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


@dataclass(frozen=True)
class SkeletonPreprocessingConfigV5:
    """Configuration for skeleton temporal normalization."""

    sequence_length: int = 30  # 2.0s at 15 Hz
    keypoint_dim: int = 4  # (norm_x, norm_y, conf, mask) per keypoint * 17 = 68
    aux_dim: int = 4  # (aspect_ratio, norm_vel_y, torso_angle, floor_prox)
    total_feature_dim: int = 72  # 68 + 4
    target_fps: float = 15.0
    # "v1": per-frame hip-centred, per-frame torso-scaled (V5/V6.1 frozen models).
    # "v2": per-window reference scale + hip trajectory channels (skeleton_features_v2).
    feature_set: str = "v1"


V2_TRAJECTORY_DIM = 7
FEATURE_SET_DIMS: dict[str, int] = {"v1": 72, "v2": 72 + V2_TRAJECTORY_DIM}
# v2 channels holding horizontal coordinates/offsets (negated on horizontal flip).
V2_X_CHANNELS: tuple[int, ...] = tuple(i * 4 for i in range(17)) + (73,)


def skeleton_features_v2(
    kpts: np.ndarray,
    bboxes: np.ndarray,
    timestamps: np.ndarray,
    image_heights: np.ndarray,
    det_confs: np.ndarray,
) -> np.ndarray:
    """View-robust (T, 79) features for ONE window; shared by training and inference.

    Per-frame pose shape is hip-centred but scaled by a single window reference scale
    (90th percentile torso length), so foreshortening and descent stay visible instead
    of being normalised away frame by frame. Trajectory channels (72..78):
    hip_dy_from_start, hip_dx_from_start, hip_vy (ref/s), head_above_hip,
    bbox_h_ratio, bbox_cy_from_start, torso_len_ratio.

    Args:
        kpts: (T, 17, 3) pixel x, y, confidence; NaN x/y marks a missing keypoint.
        bboxes: (T, 4) xyxy. timestamps: (T,) seconds.
        image_heights: (T,) pixels. det_confs: (T,) detection confidence.
    """
    t_len = kpts.shape[0]
    if kpts.shape[1:] != (17, 3) or bboxes.shape != (t_len, 4):
        raise ValueError(f"Bad window shapes: kpts {kpts.shape}, bboxes {bboxes.shape}")

    x1, y1, x2, y2 = bboxes[:, 0], bboxes[:, 1], bboxes[:, 2], bboxes[:, 3]
    bbox_w = np.maximum(x2 - x1, 1.0)
    bbox_h = np.maximum(y2 - y1, 1.0)
    valid = ~np.isnan(kpts[:, :, 0]) & ~np.isnan(kpts[:, :, 1])
    xs = np.where(valid, kpts[:, :, 0], 0.0)
    ys = np.where(valid, kpts[:, :, 1], 0.0)

    def _mid(
        a: int, b: int, fx: np.ndarray, fy: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        both = valid[:, a] & valid[:, b]
        one_x = np.where(valid[:, a], xs[:, a], xs[:, b])
        one_y = np.where(valid[:, a], ys[:, a], ys[:, b])
        mx = np.where(both, (xs[:, a] + xs[:, b]) / 2.0, one_x)
        my = np.where(both, (ys[:, a] + ys[:, b]) / 2.0, one_y)
        any_v = valid[:, a] | valid[:, b]
        return np.where(any_v, mx, fx), np.where(any_v, my, fy), any_v

    hip_x, hip_y, _ = _mid(11, 12, (x1 + x2) / 2.0, (y1 + y2) / 2.0)
    sh_x, sh_y, sh_any = _mid(5, 6, hip_x, y1)
    torso = np.where(sh_any, np.hypot(sh_x - hip_x, sh_y - hip_y), bbox_h * 0.5)
    ref_h = max(float(np.percentile(bbox_h, 90)), 1.0)
    ref = max(float(np.percentile(torso, 90)), ref_h * 0.3, 20.0)

    face = valid[:, :5]
    face_n = face.sum(axis=1)
    face_y = np.where(
        face_n > 0, (ys[:, :5] * face).sum(axis=1) / np.maximum(face_n, 1), sh_y
    )

    kp = np.zeros((t_len, 17, 4), dtype=np.float32)
    kp[:, :, 0] = np.where(valid, (xs - hip_x[:, None]) / ref, 0.0)
    kp[:, :, 1] = np.where(valid, (ys - hip_y[:, None]) / ref, 0.0)
    kp[:, :, 2] = np.nan_to_num(kpts[:, :, 2], nan=0.0)
    kp[:, :, 3] = valid.astype(np.float32)

    dx = np.abs(sh_x - hip_x)
    dy = np.abs(sh_y - hip_y)
    torso_angle = np.where(sh_any, np.degrees(np.arctan2(dy, np.maximum(dx, 1e-6))), 90.0)
    aux = np.stack(
        [
            np.clip(bbox_h / bbox_w / 3.0, 0.0, 1.0),
            np.clip(torso_angle / 90.0, 0.0, 1.0),
            np.nan_to_num(det_confs, nan=0.9),
            np.clip(hip_y / np.maximum(image_heights, 1.0), 0.0, 1.0),
        ],
        axis=-1,
    )

    dt = np.maximum(np.diff(timestamps, prepend=timestamps[0]), 1.0 / 30.0)
    cy = (y1 + y2) / 2.0
    traj = np.stack(
        [
            (hip_y - hip_y[0]) / ref,
            (hip_x - hip_x[0]) / ref,
            np.diff(hip_y, prepend=hip_y[0]) / ref / dt,
            (hip_y - face_y) / ref,
            bbox_h / ref_h,
            (cy - cy[0]) / ref,
            torso / ref,
        ],
        axis=-1,
    )
    out = np.concatenate([kp.reshape(t_len, 68), aux, traj], axis=-1)
    return np.clip(np.nan_to_num(out, nan=0.0), -10.0, 10.0).astype(np.float32)


def history_to_window_arrays(
    history: Sequence[TrackObservation | Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert observations into the raw arrays consumed by skeleton_features_v2."""
    t_len = len(history)
    kpts = np.full((t_len, 17, 3), np.nan, dtype=np.float64)
    bboxes = np.zeros((t_len, 4), dtype=np.float64)
    ts = np.zeros(t_len, dtype=np.float64)
    img_h = np.zeros(t_len, dtype=np.float64)
    confs = np.zeros(t_len, dtype=np.float64)
    for t, obs in enumerate(history):
        for i, k in enumerate(obs.keypoints[:17]):
            if k.present and k.x is not None and k.y is not None:
                kpts[t, i, 0], kpts[t, i, 1] = k.x, k.y
            kpts[t, i, 2] = k.confidence if k.confidence is not None else 0.0
        bboxes[t] = obs.bbox_xyxy
        ts[t] = obs.timestamp
        img_h[t] = float(getattr(obs, "image_height", None) or 480)
        confs[t] = float(getattr(obs, "detection_confidence", 0.9))
    return kpts, bboxes, ts, img_h, confs


def pad_window_arrays(
    arrays: tuple[np.ndarray, ...], sequence_length: int
) -> tuple[np.ndarray, ...]:
    """Keep the last ``sequence_length`` frames; left-pad by repeating the first frame."""
    t_len = arrays[0].shape[0]
    if t_len >= sequence_length:
        return tuple(a[-sequence_length:] for a in arrays)
    pad = sequence_length - t_len
    return tuple(np.concatenate([np.repeat(a[:1], pad, axis=0), a], axis=0) for a in arrays)


def extract_normalized_skeleton_frame(
    obs: TrackObservation | Any,
) -> np.ndarray:
    """Extract a 72-dimensional normalized skeleton feature vector for a single frame.

    Invariant: missing keypoints have mask=0.0 and zero coords; NEVER interpolated.
    """
    x1, y1, x2, y2 = obs.bbox_xyxy
    bbox_w = max(1.0, float(x2 - x1))
    bbox_h = max(1.0, float(y2 - y1))
    kpts: tuple[Keypoint, ...] = obs.keypoints

    # 1. Identify hip midpoint for centering
    l_hip, r_hip = kpts[11], kpts[12]
    if (
        l_hip.present
        and r_hip.present
        and l_hip.x is not None
        and r_hip.x is not None
        and l_hip.y is not None
        and r_hip.y is not None
    ):
        hip_x = (l_hip.x + r_hip.x) / 2.0
        hip_y = (l_hip.y + r_hip.y) / 2.0
    elif l_hip.present and l_hip.x is not None and l_hip.y is not None:
        hip_x, hip_y = l_hip.x, l_hip.y
    elif r_hip.present and r_hip.x is not None and r_hip.y is not None:
        hip_x, hip_y = r_hip.x, r_hip.y
    else:
        hip_x, hip_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0

    # 2. Identify torso length for scale invariance
    l_sh, r_sh = kpts[5], kpts[6]
    if (
        l_sh.present
        and r_sh.present
        and l_sh.x is not None
        and r_sh.x is not None
        and l_sh.y is not None
        and r_sh.y is not None
    ):
        sh_x = (l_sh.x + r_sh.x) / 2.0
        sh_y = (l_sh.y + r_sh.y) / 2.0
        torso_len = math.sqrt((sh_x - hip_x) ** 2 + (sh_y - hip_y) ** 2)
    else:
        torso_len = bbox_h * 0.5

    scale = max(torso_len, bbox_h * 0.3, 20.0)

    # 3. Normalize 17 keypoints
    kp_features = np.zeros((17, 4), dtype=np.float32)
    for i, kp in enumerate(kpts):
        if kp.present and kp.x is not None and kp.y is not None:
            norm_x = (kp.x - hip_x) / scale
            norm_y = (kp.y - hip_y) / scale
            kp_features[i] = [norm_x, norm_y, float(kp.confidence), 1.0]
        else:
            kp_features[i] = [
                0.0,
                0.0,
                float(kp.confidence) if kp.confidence is not None else 0.0,
                0.0,
            ]

    flat_kp = kp_features.flatten()  # 68 values

    # 4. Auxiliary geometric features
    aspect_ratio = bbox_h / bbox_w
    torso_angle = 90.0
    if l_sh.present and r_sh.present and l_sh.x is not None and l_sh.y is not None:
        dx = abs((l_sh.x + r_sh.x) / 2.0 - hip_x)
        dy = abs((l_sh.y + r_sh.y) / 2.0 - hip_y)
        torso_angle = math.degrees(math.atan2(dy, max(dx, 1e-6)))

    norm_torso_angle = torso_angle / 90.0  # [0, 1]
    norm_aspect = min(aspect_ratio / 3.0, 1.0)
    conf_mean = float(obs.detection_confidence) if hasattr(obs, "detection_confidence") else 0.9
    floor_prox = max(0.0, min(1.0, hip_y / max(getattr(obs, "image_height", 480), 1.0)))

    aux = np.array([norm_aspect, norm_torso_angle, conf_mean, floor_prox], dtype=np.float32)

    return np.concatenate([flat_kp, aux])


def extract_skeleton_sequence_tensor(
    history: Sequence[TrackObservation | Any],
    sequence_length: int = 30,
    feature_set: str = "v1",
) -> np.ndarray:
    """Transform observation history into a fixed-length (sequence_length, D) feature array."""
    if feature_set not in FEATURE_SET_DIMS:
        raise ValueError(f"Unknown feature_set '{feature_set}'")
    if not history:
        return np.zeros((sequence_length, FEATURE_SET_DIMS[feature_set]), dtype=np.float32)
    if feature_set == "v2":
        window = pad_window_arrays(
            history_to_window_arrays(history[-sequence_length:]), sequence_length
        )
        return skeleton_features_v2(*window)

    frames_vecs = [extract_normalized_skeleton_frame(obs) for obs in history]
    if len(frames_vecs) >= sequence_length:
        return np.array(frames_vecs[-sequence_length:], dtype=np.float32)
    else:
        # Pad at start with first available frame
        pad_count = sequence_length - len(frames_vecs)
        pad_frame = frames_vecs[0]
        padded = [pad_frame] * pad_count + frames_vecs
        return np.array(padded, dtype=np.float32)


def augment_skeleton_sequence_tensor(
    tensor: np.ndarray,
    flip_p: float = 0.5,
    max_rot_deg: float = 8.0,
    scale_range: tuple[float, float] = (0.9, 1.1),
) -> np.ndarray:
    """Apply viewpoint augmentations: horizontal flip with L/R keypoint swap, rotation, and scaling."""
    aug = tensor.copy()
    t_len = aug.shape[0]

    do_flip = np.random.rand() < flip_p
    rot_deg = np.random.uniform(-max_rot_deg, max_rot_deg)
    rot_rad = math.radians(rot_deg)
    scale = np.random.uniform(scale_range[0], scale_range[1])
    cos_a = math.cos(rot_rad)
    sin_a = math.sin(rot_rad)

    # Keypoint pairs for horizontal flip: (Left, Right)
    swap_pairs = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]

    for t in range(t_len):
        kps = aug[t, :68].reshape(17, 4).copy()

        # 1. Flip X coordinate and swap keypoint pairs
        if do_flip:
            kps[:, 0] = -kps[:, 0]
            for l_idx, r_idx in swap_pairs:
                tmp = kps[l_idx].copy()
                kps[l_idx] = kps[r_idx]
                kps[r_idx] = tmp

        # 2. 2D rotation & scale jitter
        xs = kps[:, 0].copy()
        ys = kps[:, 1].copy()
        masks = kps[:, 3] > 0.5

        new_xs = (xs * cos_a - ys * sin_a) * scale
        new_ys = (xs * sin_a + ys * cos_a) * scale

        kps[:, 0] = np.where(masks, new_xs, 0.0)
        kps[:, 1] = np.where(masks, new_ys, 0.0)

        aug[t, :68] = kps.flatten()

    return aug.astype(np.float32)


class TemporalSkeletonNetV5(nn.Module):
    """Deep 1D CNN-GRU Temporal Classifier for 3-class Fall Action Recognition."""

    def __init__(
        self,
        in_features: int = 72,
        conv_channels: int = 64,
        gru_hidden: int = 64,
        num_classes: int = 3,  # 0: Normal, 1: Falling, 2: Fallen
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(in_features, conv_channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm1d(conv_channels)
        self.relu = nn.ReLU()
        self.conv2 = nn.Conv1d(conv_channels, conv_channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm1d(conv_channels)
        self.dropout = nn.Dropout(dropout)

        self.gru = nn.GRU(
            input_size=conv_channels,
            hidden_size=gru_hidden,
            num_layers=2,
            batch_first=True,
            bidirectional=True,
            dropout=dropout,
        )

        self.fc = nn.Sequential(
            nn.Linear(gru_hidden * 2, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (B, T, 72) -> transpose to (B, 72, T) for Conv1d
        x_trans = x.transpose(1, 2)
        c1 = self.dropout(self.relu(self.bn1(self.conv1(x_trans))))
        c2 = self.dropout(self.relu(self.bn2(self.conv2(c1))))

        # Transpose back to (B, T, channels) for GRU
        gru_in = c2.transpose(1, 2)
        out, _ = self.gru(gru_in)  # (B, T, gru_hidden * 2)

        # Global temporal max-pooling + final step representation
        last_step = out[:, -1, :]
        max_pooled, _ = torch.max(out, dim=1)
        fused = (last_step + max_pooled) / 2.0

        logits = self.fc(fused)  # (B, 3)
        return logits


class TemporalSkeletonClassifierV5:
    """Production wrapper for V5 Temporal Skeleton Neural Network."""

    def __init__(
        self,
        model: TemporalSkeletonNetV5 | None = None,
        config: SkeletonPreprocessingConfigV5 | None = None,
    ) -> None:
        self.config = config or SkeletonPreprocessingConfigV5()
        self.model = model or TemporalSkeletonNetV5(in_features=self.config.total_feature_dim)
        self.model.eval()

    def predict_probabilities(
        self, history: Sequence[TrackObservation | Any]
    ) -> tuple[float, float, float]:
        """Predict 3-class probabilities: (p_normal, p_falling, p_fallen)."""
        feat_arr = extract_skeleton_sequence_tensor(
            history,
            sequence_length=self.config.sequence_length,
            feature_set=self.config.feature_set,
        )
        x_t = torch.from_numpy(feat_arr).unsqueeze(0)  # (1, T, 72)

        with torch.no_grad():
            logits = self.model(x_t)
            probs = F.softmax(logits, dim=-1).squeeze(0).cpu().numpy()

        return float(probs[0]), float(probs[1]), float(probs[2])

    def predict_fall_confidence(self, history: Sequence[TrackObservation | Any]) -> float:
        """Derive unified fall confidence score from falling and fallen probabilities."""
        p_normal, p_falling, p_fallen = self.predict_probabilities(history)
        # Combined fall indicator
        return float(p_falling * 0.4 + p_fallen * 0.6)

    def save(self, path: str | Path) -> None:
        """Save model weights, config, and training metadata to file."""
        dest = Path(path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "sequence_length": self.config.sequence_length,
                "total_feature_dim": self.config.total_feature_dim,
                "feature_set": self.config.feature_set,
                "training_sequence_ids": getattr(self, "training_sequence_ids", []),
                "manifest_sha256": getattr(self, "manifest_sha256", ""),
                "trained_at": getattr(self, "trained_at", ""),
            },
            dest,
        )

    @classmethod
    def load(cls, path: str | Path) -> TemporalSkeletonClassifierV5:
        """Load model weights, config, and training metadata from file."""
        src = Path(path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Model file not found: {src}")

        checkpoint = torch.load(src, map_location="cpu", weights_only=True)
        cfg = SkeletonPreprocessingConfigV5(
            sequence_length=checkpoint.get("sequence_length", 30),
            total_feature_dim=checkpoint.get("total_feature_dim", 72),
            feature_set=checkpoint.get("feature_set", "v1"),
        )
        net = TemporalSkeletonNetV5(in_features=cfg.total_feature_dim)
        net.load_state_dict(checkpoint["state_dict"])
        net.eval()
        inst = cls(model=net, config=cfg)
        inst.training_sequence_ids = checkpoint.get("training_sequence_ids", [])
        inst.manifest_sha256 = checkpoint.get("manifest_sha256", "")
        inst.trained_at = checkpoint.get("trained_at", "")
        return inst
