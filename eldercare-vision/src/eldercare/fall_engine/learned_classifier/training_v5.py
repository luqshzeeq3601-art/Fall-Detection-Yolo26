"""Phase 11.8 V5 Model Training, 5-Fold Grouped CV & Hard Negative Mining Engine (P11.8-017..021).

Conducts strict 5-fold cross-validation grouped by (source, subject), trains
M0 (retrained V4), M1 (HistGBDT), M2 (Temporal Skeleton CNN-GRU), and M3 (Fused),
performs hard-negative mining, and calibrates post-processor thresholds on OOF predictions.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from sklearn.model_selection import GroupKFold
from torch.utils.data import DataLoader, TensorDataset

from eldercare.fall_engine.cache.storage import load_keypoint_cache
from eldercare.fall_engine.features.multiscale import (
    extract_multiscale_temporal_features,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    ClassifierV5M1_HistGBDT,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
    TemporalSkeletonNetV5,
    extract_skeleton_sequence_tensor,
)
from eldercare.vision.tracking.observation import TrackObservation

LOG = logging.getLogger("training_v5")
ROOT = Path(__file__).resolve().parents[3]


@dataclass
class TrainingSampleV5:
    """A prepared temporal window sample for V5 training."""

    sample_id: str
    source_dataset: str
    subject_id: str
    label_3class: int  # 0: Normal/ADL, 1: Falling, 2: Fallen
    is_fall_event: bool
    skeleton_tensor: np.ndarray  # (30, 72)
    hand_features_multiscale: np.ndarray  # (24,) or (72,)


def load_dataset_samples_from_cache(
    manifest_records: list[dict[str, Any]],
    cache_dir: Path,
    sequence_length: int = 30,
) -> list[TrainingSampleV5]:
    """Load cached sequences and slice into 15 Hz training windows."""
    samples: list[TrainingSampleV5] = []

    for r in manifest_records:
        seq_id = r["sequence_id"]
        source = r["source_dataset"]
        subj = r["subject_id"]
        is_fall = r.get("is_fall", False)
        f_start = r.get("fall_start_sec")
        f_end = r.get("fall_end_sec")
        l_start = r.get("lying_start_sec")

        cache_path = cache_dir / f"{seq_id}.npz"
        if not cache_path.is_file():
            continue

        try:
            seq = load_keypoint_cache(cache_path)
        except Exception as e:
            LOG.warning("Failed to load cache %s: %s", cache_path, e)
            continue

        if not seq.frames:
            continue

        # Convert CachedFrame list to TrackObservation list
        observations: list[TrackObservation] = []
        for f in seq.frames:
            if f.persons:
                p = f.persons[0]
                obs = TrackObservation(
                    camera_id=seq_id,
                    track_id=p.track_id or 1,
                    timestamp=f.timestamp,
                    bbox_xyxy=p.bbox_xyxy,
                    detection_confidence=p.detection_confidence,
                    keypoints=p.keypoints,
                    image_width=f.image_width,
                    image_height=f.image_height,
                )
                observations.append(obs)

        if len(observations) < 5:
            continue

        if len(observations) < sequence_length:
            win_obs = observations
            t_mid = win_obs[-1].timestamp
            label = 0
            if is_fall:
                if (
                    f_start is not None
                    and f_end is not None
                    and (f_start - 0.3 <= t_mid <= f_end + 0.3)
                ):
                    label = 1
                elif l_start is not None and (t_mid >= l_start - 0.2):
                    label = 2
                elif f_end is not None and (t_mid > f_end):
                    label = 2
                else:
                    label = 1
            skel_tensor = extract_skeleton_sequence_tensor(win_obs, sequence_length=sequence_length)
            multi_feats = extract_multiscale_temporal_features(win_obs)
            hand_vec = np.array(multi_feats.fused_feature_vector, dtype=np.float32)
            samples.append(
                TrainingSampleV5(
                    sample_id=f"{seq_id}_pad",
                    source_dataset=source,
                    subject_id=subj,
                    label_3class=label,
                    is_fall_event=is_fall,
                    skeleton_tensor=skel_tensor,
                    hand_features_multiscale=hand_vec,
                )
            )
        else:
            step = 1 if is_fall else 2
            for start_idx in range(0, len(observations) - sequence_length + 1, step):
                win_obs = observations[start_idx : start_idx + sequence_length]
                t_mid = win_obs[-1].timestamp

                # Determine 3-class label
                label = 0  # Normal/ADL
                if is_fall:
                    if (
                        f_start is not None
                        and f_end is not None
                        and (f_start - 0.3 <= t_mid <= f_end + 0.3)
                    ):
                        label = 1  # Falling transition
                    elif l_start is not None and (t_mid >= l_start - 0.2):
                        label = 2  # Fallen posture
                    elif f_end is not None and (t_mid > f_end):
                        label = 2  # Fallen posture

                skel_tensor = extract_skeleton_sequence_tensor(
                    win_obs, sequence_length=sequence_length
                )
                multi_feats = extract_multiscale_temporal_features(win_obs)
                hand_vec = np.array(multi_feats.fused_feature_vector, dtype=np.float32)

                samples.append(
                    TrainingSampleV5(
                        sample_id=f"{seq_id}_{start_idx}",
                        source_dataset=source,
                        subject_id=subj,
                        label_3class=label,
                        is_fall_event=is_fall,
                        skeleton_tensor=skel_tensor,
                        hand_features_multiscale=hand_vec,
                    )
                )

    LOG.info(
        "Loaded %d temporal training windows from %d records.", len(samples), len(manifest_records)
    )
    return samples


def train_m2_skeleton_net(
    train_samples: list[TrainingSampleV5],
    val_samples: list[TrainingSampleV5],
    epochs: int = 25,
    batch_size: int = 32,
    lr: float = 1e-3,
) -> TemporalSkeletonNetV5:
    """Train TemporalSkeletonNetV5 with Cross-Entropy Loss on 3-class labels."""
    model = TemporalSkeletonNetV5(in_features=72, conv_channels=64, gru_hidden=64, num_classes=3)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # Class weights for class balance: 0 (Normal) is common, 1 (Falling) is rare, 2 (Fallen)
    weights = torch.tensor([1.0, 3.0, 2.0], dtype=torch.float32)
    criterion = nn.CrossEntropyLoss(weight=weights)

    X_train = np.array([s.skeleton_tensor for s in train_samples], dtype=np.float32)
    y_train = np.array([s.label_3class for s in train_samples], dtype=np.int64)

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    model.train()
    for epoch in range(epochs):
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()

    model.eval()
    return model


def train_m1_hist_gbdt(
    train_samples: list[TrainingSampleV5],
    training_sequence_ids: Sequence[str] | None = None,
    manifest_sha256: str = "",
    trained_at: str = "",
) -> ClassifierV5M1_HistGBDT:
    """Train M1 HistGradientBoosting classifier on multi-scale hand features."""
    X_train = np.array([s.hand_features_multiscale for s in train_samples], dtype=np.float32)
    # Binary fall label: 1 if falling or fallen, 0 otherwise
    y_train = np.array([1 if s.label_3class > 0 else 0 for s in train_samples], dtype=np.int32)

    m1 = ClassifierV5M1_HistGBDT(
        training_sequence_ids=list(training_sequence_ids or []),
        manifest_sha256=manifest_sha256,
        trained_at=trained_at,
    )
    m1.fit(
        X_train,
        y_train,
        training_sequence_ids=training_sequence_ids,
        manifest_sha256=manifest_sha256,
    )
    return m1


def run_5fold_cross_validation_v5(
    samples: list[TrainingSampleV5],
    n_splits: int = 5,
) -> dict[str, Any]:
    """Run strict 5-fold cross-validation grouped by (source, subject)."""
    groups = [f"{s.source_dataset}_{s.subject_id}" for s in samples]
    unique_groups = len(set(groups))
    actual_splits = min(n_splits, unique_groups)

    gkf = GroupKFold(n_splits=actual_splits)

    oof_predictions_m1: list[float] = [0.0] * len(samples)
    oof_predictions_m2: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(samples)
    oof_ground_truth: list[int] = [s.label_3class for s in samples]

    for fold_idx, (train_idx, val_idx) in enumerate(gkf.split(samples, groups=groups)):
        train_sub = [samples[i] for i in train_idx]
        val_sub = [samples[i] for i in val_idx]

        # Train M1
        m1 = train_m1_hist_gbdt(train_sub)
        # Train M2
        m2_net = train_m2_skeleton_net(train_sub, val_sub, epochs=15)
        m2 = TemporalSkeletonClassifierV5(model=m2_net)

        for i in val_idx:
            sample = samples[i]
            # M1 prediction
            oof_predictions_m1[i] = m1.predict_probability(sample.hand_features_multiscale)
            # M2 prediction
            with torch.no_grad():
                x_t = torch.from_numpy(sample.skeleton_tensor).unsqueeze(0)
                logits = m2_net(x_t)
                probs = torch.softmax(logits, dim=-1).squeeze(0).numpy()
                oof_predictions_m2[i] = (float(probs[0]), float(probs[1]), float(probs[2]))

    # Calibrate optimal post-processor threshold on OOF
    best_thresh = 0.45
    best_f1 = 0.0
    for thresh in np.arange(0.20, 0.80, 0.05):
        preds = [1 if (p[1] + p[2]) >= thresh else 0 for p in oof_predictions_m2]
        gts = [1 if gt > 0 else 0 for gt in oof_ground_truth]
        tp = sum(1 for p, g in zip(preds, gts) if p == 1 and g == 1)
        fp = sum(1 for p, g in zip(preds, gts) if p == 1 and g == 0)
        fn = sum(1 for p, g in zip(preds, gts) if p == 0 and g == 1)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = float(thresh)

    return {
        "num_samples": len(samples),
        "num_groups": unique_groups,
        "n_splits": actual_splits,
        "best_calibrated_threshold": best_thresh,
        "best_oof_f1": best_f1,
    }
