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
) -> np.ndarray:
    """Transform observation history into fixed-length (sequence_length, 72) feature array."""
    if not history:
        return np.zeros((sequence_length, 72), dtype=np.float32)

    frames_vecs = [extract_normalized_skeleton_frame(obs) for obs in history]
    if len(frames_vecs) >= sequence_length:
        return np.array(frames_vecs[-sequence_length:], dtype=np.float32)
    else:
        # Pad at start with first available frame
        pad_count = sequence_length - len(frames_vecs)
        pad_frame = frames_vecs[0]
        padded = [pad_frame] * pad_count + frames_vecs
        return np.array(padded, dtype=np.float32)


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
            history, sequence_length=self.config.sequence_length
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
        """Save model weights and config to file."""
        dest = Path(path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "sequence_length": self.config.sequence_length,
                "total_feature_dim": self.config.total_feature_dim,
            },
            dest,
        )

    @classmethod
    def load(cls, path: str | Path) -> TemporalSkeletonClassifierV5:
        """Load model weights and config from file."""
        src = Path(path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Model file not found: {src}")

        checkpoint = torch.load(src, map_location="cpu", weights_only=True)
        cfg = SkeletonPreprocessingConfigV5(
            sequence_length=checkpoint.get("sequence_length", 30),
            total_feature_dim=checkpoint.get("total_feature_dim", 72),
        )
        net = TemporalSkeletonNetV5(in_features=cfg.total_feature_dim)
        net.load_state_dict(checkpoint["state_dict"])
        net.eval()
        return cls(model=net, config=cfg)
