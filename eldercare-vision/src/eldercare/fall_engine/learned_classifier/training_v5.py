"""Phase 11.8 V5 Model Training, 5-Fold Grouped CV & Hard Negative Mining Engine (P11.8-017..021).

Conducts strict 5-fold cross-validation grouped by (source, subject), trains
M0 (retrained V4), M1 (HistGBDT), M2 (Temporal Skeleton CNN-GRU), and M3 (Fused),
performs hard-negative mining, and calibrates post-processor thresholds on OOF predictions.
"""

from __future__ import annotations

import json
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

from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    ClassifierV5M1_HistGBDT,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
    TemporalSkeletonNetV5,
)

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
        is_fall = bool(r.get("is_fall", False))
        f_start = r.get("fall_start_sec")
        f_end = r.get("fall_end_sec")
        l_start = r.get("lying_start_sec")

        cache_path = cache_dir / f"{seq_id}.npz"
        if not cache_path.is_file():
            continue

        try:
            with np.load(cache_path, allow_pickle=False) as npz_data:
                kpts_arr = npz_data["keypoints"]
                bboxes_arr = npz_data["bboxes"]
                timestamps_arr = npz_data["timestamps"]
                dims_arr = npz_data["dims"] if "dims" in npz_data else np.tile([640, 480], (len(timestamps_arr), 1))
                confs_arr = (
                    npz_data["confidences"]
                    if "confidences" in npz_data
                    else np.full(len(timestamps_arr), 0.9, dtype=np.float32)
                )
        except Exception as e:
            LOG.warning("Failed to load cache %s: %s", cache_path, e)
            continue

        T = len(timestamps_arr)
        if T < 5:
            continue

        # Vectorized extraction of (T, 72) skeleton feature matrix
        x1 = bboxes_arr[:, 0]
        y1 = bboxes_arr[:, 1]
        x2 = bboxes_arr[:, 2]
        y2 = bboxes_arr[:, 3]
        bbox_w = np.maximum(x2 - x1, 1.0)
        bbox_h = np.maximum(y2 - y1, 1.0)

        # Hips (11: L hip, 12: R hip)
        l_hip_present = ~np.isnan(kpts_arr[:, 11, 0])
        r_hip_present = ~np.isnan(kpts_arr[:, 12, 0])
        both_hips = l_hip_present & r_hip_present
        hip_x = np.where(both_hips, (kpts_arr[:, 11, 0] + kpts_arr[:, 12, 0]) / 2.0, (x1 + x2) / 2.0)
        hip_y = np.where(both_hips, (kpts_arr[:, 11, 1] + kpts_arr[:, 12, 1]) / 2.0, (y1 + y2) / 2.0)

        # Shoulders (5: L shoulder, 6: R shoulder)
        l_sh_present = ~np.isnan(kpts_arr[:, 5, 0])
        r_sh_present = ~np.isnan(kpts_arr[:, 6, 0])
        sh_present = l_sh_present & r_sh_present
        sh_x = (kpts_arr[:, 5, 0] + kpts_arr[:, 6, 0]) / 2.0
        sh_y = (kpts_arr[:, 5, 1] + kpts_arr[:, 6, 1]) / 2.0
        torso_len = np.where(sh_present, np.sqrt((sh_x - hip_x) ** 2 + (sh_y - hip_y) ** 2), bbox_h * 0.5)
        scale = np.maximum(torso_len, np.maximum(bbox_h * 0.3, 20.0))

        # 17 normalized keypoints (T, 17, 4)
        kp_feats = np.zeros((T, 17, 4), dtype=np.float32)
        valid_kp = ~np.isnan(kpts_arr[:, :, 0]) & ~np.isnan(kpts_arr[:, :, 1])
        kp_feats[:, :, 0] = np.where(valid_kp, (kpts_arr[:, :, 0] - hip_x[:, None]) / scale[:, None], 0.0)
        kp_feats[:, :, 1] = np.where(valid_kp, (kpts_arr[:, :, 1] - hip_y[:, None]) / scale[:, None], 0.0)
        kp_feats[:, :, 2] = np.nan_to_num(kpts_arr[:, :, 2], nan=0.0)
        kp_feats[:, :, 3] = np.where(valid_kp, 1.0, 0.0)
        flat_kps = kp_feats.reshape(T, 68)

        # Auxiliary features
        aspect_ratio = bbox_h / bbox_w
        dx = np.abs(sh_x - hip_x)
        dy = np.abs(sh_y - hip_y)
        torso_angle = np.where(sh_present, np.degrees(np.arctan2(dy, np.maximum(dx, 1e-6))), 90.0)
        norm_torso_angle = np.clip(torso_angle / 90.0, 0.0, 1.0)
        norm_aspect = np.clip(aspect_ratio / 3.0, 0.0, 1.0)
        conf_mean = np.nan_to_num(confs_arr, nan=0.9)
        img_h = np.maximum(dims_arr[:, 1], 1.0)
        floor_prox = np.clip(hip_y / img_h, 0.0, 1.0)

        aux_feats = np.stack([norm_aspect, norm_torso_angle, conf_mean, floor_prox], axis=-1).astype(np.float32)
        seq_skel_vecs = np.concatenate([flat_kps, aux_feats], axis=-1).astype(np.float32)  # (T, 72)

        is_longform = bool(r.get("is_long_form", False) or T > 1000)
        step = 120 if is_longform else (6 if is_fall else 24)

        if T < sequence_length:
            pad_count = sequence_length - T
            padded = np.pad(seq_skel_vecs, ((pad_count, 0), (0, 0)), mode="edge")
            t_mid = timestamps_arr[-1]
            label = 0
            if is_fall:
                if f_start is not None and f_end is not None and (f_start - 0.3 <= t_mid <= f_end + 0.3):
                    label = 1
                elif l_start is not None and (t_mid >= l_start - 0.2):
                    label = 2
                elif f_end is not None and (t_mid > f_end):
                    label = 2
                else:
                    label = 1

            hand_vec = np.pad(seq_skel_vecs[-1, -24:], (0, max(0, 24 - seq_skel_vecs.shape[1])), mode="constant")[:24]
            samples.append(
                TrainingSampleV5(
                    sample_id=f"{seq_id}_pad",
                    source_dataset=source,
                    subject_id=subj,
                    label_3class=label,
                    is_fall_event=is_fall,
                    skeleton_tensor=padded,
                    hand_features_multiscale=hand_vec,
                )
            )
        else:
            for start_idx in range(0, T - sequence_length + 1, step):
                win_skel = seq_skel_vecs[start_idx : start_idx + sequence_length]
                t_mid = timestamps_arr[start_idx + sequence_length - 1]

                label = 0
                if is_fall:
                    if f_start is not None and f_end is not None and (f_start - 0.3 <= t_mid <= f_end + 0.3):
                        label = 1
                    elif l_start is not None and (t_mid >= l_start - 0.2):
                        label = 2
                    elif f_end is not None and (t_mid > f_end):
                        label = 2

                hand_vec = win_skel[-1, -24:]
                samples.append(
                    TrainingSampleV5(
                        sample_id=f"{seq_id}_{start_idx}",
                        source_dataset=source,
                        subject_id=subj,
                        label_3class=label,
                        is_fall_event=is_fall,
                        skeleton_tensor=win_skel,
                        hand_features_multiscale=hand_vec,
                    )
                )

    LOG.info(
        "Loaded %d temporal training windows from %d records.", len(samples), len(manifest_records)
    )
    return samples


def augment_batch_tensors(batch_x: torch.Tensor) -> torch.Tensor:
    """Fast tensor-based augmentation for skeleton sequence batches."""
    B, T, D = batch_x.shape
    aug = batch_x.clone()

    # Random horizontal flip
    flip_mask = torch.rand(B, device=batch_x.device) < 0.5
    if flip_mask.any():
        for kp_idx in range(17):
            aug[flip_mask, :, kp_idx * 4] = -aug[flip_mask, :, kp_idx * 4]

        swap_pairs = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]
        for l_idx, r_idx in swap_pairs:
            l_slice = aug[flip_mask, :, l_idx * 4 : (l_idx + 1) * 4].clone()
            r_slice = aug[flip_mask, :, r_idx * 4 : (r_idx + 1) * 4].clone()
            aug[flip_mask, :, l_idx * 4 : (l_idx + 1) * 4] = r_slice
            aug[flip_mask, :, r_idx * 4 : (r_idx + 1) * 4] = l_slice

    # Random scale jitter (0.95 to 1.05)
    scales = 0.95 + torch.rand(B, 1, 1, device=batch_x.device) * 0.10
    for kp_idx in range(17):
        aug[:, :, kp_idx * 4] *= scales.squeeze(-1)
        aug[:, :, kp_idx * 4 + 1] *= scales.squeeze(-1)

    return aug


def train_m2_skeleton_net(
    train_samples: list[TrainingSampleV5],
    val_samples: list[TrainingSampleV5],
    epochs: int = 10,
    batch_size: int = 256,
    lr: float = 1e-3,
    seed: int = 42,
    patience: int = 3,
    augment: bool = True,
) -> TemporalSkeletonNetV5:
    """Train TemporalSkeletonNetV5 with Cross-Entropy Loss, early stopping, and data augmentation."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = TemporalSkeletonNetV5(in_features=72, conv_channels=64, gru_hidden=64, num_classes=3)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # Class balance weights: 0 (Normal)=1.0, 1 (Falling)=3.5, 2 (Fallen)=2.0
    weights = torch.tensor([1.0, 3.5, 2.0], dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)

    X_train = np.array([s.skeleton_tensor for s in train_samples], dtype=np.float32)
    y_train = np.array([s.label_3class for s in train_samples], dtype=np.int64)

    X_val = (
        np.array([s.skeleton_tensor for s in val_samples], dtype=np.float32)
        if val_samples
        else None
    )
    y_val = (
        np.array([s.label_3class for s in val_samples], dtype=np.int64)
        if val_samples
        else None
    )

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)

    best_loss = float("inf")
    best_weights = None
    no_improve = 0

    for epoch in range(epochs):
        model.train()
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            if augment:
                batch_x = augment_batch_tensors(batch_x)

            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()

        # Validation step for early stopping
        if X_val is not None and len(X_val) > 0:
            model.eval()
            val_ds = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val))
            val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
            val_loss = 0.0
            total_val_batches = 0
            with torch.no_grad():
                for v_x, v_y in val_loader:
                    v_x, v_y = v_x.to(device), v_y.to(device)
                    v_logits = model(v_x)
                    v_l = criterion(v_logits, v_y)
                    val_loss += float(v_l.item())
                    total_val_batches += 1

            avg_val_loss = val_loss / max(1, total_val_batches)
            if avg_val_loss < best_loss:
                best_loss = avg_val_loss
                best_weights = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
                if no_improve >= patience:
                    break

    if best_weights is not None:
        model.load_state_dict({k: v.to(device) for k, v in best_weights.items()})

    model.eval()
    model.to(torch.device("cpu"))
    return model


def train_m1_hist_gbdt(
    train_samples: list[TrainingSampleV5],
    training_sequence_ids: Sequence[str] | None = None,
    manifest_sha256: str = "",
    trained_at: str = "",
) -> ClassifierV5M1_HistGBDT:
    """Train M1 HistGradientBoosting classifier on multi-scale hand features."""
    X_train = np.array([s.hand_features_multiscale for s in train_samples], dtype=np.float32)
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


def sample_group_key(source_dataset: str, subject_id: str) -> str:
    """CV grouping key shared by training and fold-aware calibration."""
    return f"{source_dataset}_{subject_id}"


def _split_inner_validation(
    train_idx: np.ndarray,
    groups: list[str],
    seed: int,
    val_fraction: float = 0.15,
) -> tuple[list[int], list[int]]:
    """Hold out whole groups from the fold's training set for early stopping."""
    train_groups = sorted({groups[i] for i in train_idx})
    rng = np.random.default_rng(seed)
    n_val = max(1, int(round(len(train_groups) * val_fraction))) if len(train_groups) > 1 else 0
    val_groups = set(rng.choice(train_groups, size=n_val, replace=False).tolist()) if n_val else set()
    fit_idx = [int(i) for i in train_idx if groups[i] not in val_groups]
    inner_val_idx = [int(i) for i in train_idx if groups[i] in val_groups]
    return fit_idx, inner_val_idx


def run_5fold_cross_validation_v5(
    samples: list[TrainingSampleV5],
    n_splits: int = 5,
    epochs: int = 10,
    fold_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run strict 5-fold cross-validation grouped by (source, subject).

    Early stopping uses an inner validation split carved from each fold's training
    groups, so out-of-fold predictions never influence model selection. When
    ``fold_output_dir`` is set, each fold's M2 model and the group -> fold
    assignment are saved for fold-aware event-level calibration.
    """
    groups = [sample_group_key(s.source_dataset, s.subject_id) for s in samples]
    unique_groups = len(set(groups))
    actual_splits = min(n_splits, unique_groups)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    gkf = GroupKFold(n_splits=actual_splits)

    oof_predictions_m1: list[float] = [0.0] * len(samples)
    oof_predictions_m2: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(samples)
    oof_ground_truth: list[int] = [s.label_3class for s in samples]
    group_to_fold: dict[str, int] = {}

    if fold_output_dir is not None:
        fold_output_dir.mkdir(parents=True, exist_ok=True)

    for fold_idx, (train_idx, val_idx) in enumerate(gkf.split(samples, groups=groups)):
        LOG.info("Training CV fold %d/%d...", fold_idx + 1, actual_splits)
        for i in val_idx:
            group_to_fold[groups[i]] = fold_idx

        fit_idx, inner_val_idx = _split_inner_validation(train_idx, groups, seed=42 + fold_idx)
        fit_sub = [samples[i] for i in fit_idx]
        inner_val_sub = [samples[i] for i in inner_val_idx]
        train_sub = [samples[i] for i in train_idx]

        # Train M1
        m1 = train_m1_hist_gbdt(train_sub)
        # Train M2 with an inner (non-OOF) validation split for early stopping
        m2_net = train_m2_skeleton_net(fit_sub, inner_val_sub, epochs=epochs, seed=42 + fold_idx)

        if fold_output_dir is not None:
            TemporalSkeletonClassifierV5(model=m2_net).save(
                fold_output_dir / f"m2_fold_{fold_idx}.pt"
            )

        # Batch M2 validation prediction
        val_X = np.array([samples[i].skeleton_tensor for i in val_idx], dtype=np.float32)
        val_ds = TensorDataset(torch.from_numpy(val_X))
        val_loader = DataLoader(val_ds, batch_size=256, shuffle=False)
        # train_m2_skeleton_net returns the model on CPU; predict on the training device.
        m2_net.to(device)
        m2_net.eval()
        all_probs = []
        with torch.no_grad():
            for (bx,) in val_loader:
                logits = m2_net(bx.to(device))
                p = torch.softmax(logits, dim=-1).cpu().numpy()
                all_probs.append(p)
        val_m2_probs = np.concatenate(all_probs, axis=0)

        # Batch M1 validation prediction
        val_m1_X = np.array([samples[i].hand_features_multiscale for i in val_idx], dtype=np.float32)
        val_m1_probs = (
            m1.model.predict_proba(val_m1_X)[:, 1]
            if hasattr(m1.model, "predict_proba")
            else np.zeros(len(val_idx))
        )

        for k, i in enumerate(val_idx):
            oof_predictions_m1[i] = float(val_m1_probs[k])
            p_k = val_m2_probs[k]
            oof_predictions_m2[i] = (float(p_k[0]), float(p_k[1]), float(p_k[2]))

    # Calibrate optimal kinetic falling trigger threshold on OOF
    best_thresh = 0.45
    best_f1 = 0.0
    best_recall = 0.0
    best_precision = 0.0
    for thresh in np.arange(0.20, 0.80, 0.05):
        preds = [1 if p[1] >= thresh else 0 for p in oof_predictions_m2]
        gts = [1 if gt == 1 else 0 for gt in oof_ground_truth]
        tp = sum(1 for p, g in zip(preds, gts) if p == 1 and g == 1)
        fp = sum(1 for p, g in zip(preds, gts) if p == 1 and g == 0)
        fn = sum(1 for p, g in zip(preds, gts) if p == 0 and g == 1)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = float(thresh)
            best_recall = rec
            best_precision = prec

    if fold_output_dir is not None:
        (fold_output_dir / "fold_assignment.json").write_text(
            json.dumps(
                {"n_splits": actual_splits, "group_to_fold": group_to_fold}, indent=2
            ),
            encoding="utf-8",
        )

    return {
        "num_samples": len(samples),
        "num_groups": unique_groups,
        "n_splits": actual_splits,
        "best_calibrated_threshold": best_thresh,
        "best_oof_f1": best_f1,
        "oof_f1": best_f1,
        "oof_recall": best_recall,
        "oof_precision": best_precision,
    }
