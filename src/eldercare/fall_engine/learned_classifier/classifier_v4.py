# ruff: noqa: N803, N806, N812, B905, E501
"""Phase 11.7 V4 Temporal Fall Classifier Family & Implementations.

Architectures for scale-normalized, real-video temporal fall classification:
- LogisticClassifierV4: L2-regularized linear model with explainable feature contributions.
- MLPClassifierV4: Multi-Layer Perceptron with LayerNorm, ReLU, Dropout, and Focal Loss.
- TCNClassifierV4: 1D Causal Dilated Temporal Convolutional Network.
- GRUClassifierV4: Recurrent Gated Network with temporal aggregation.
- EnsembleClassifierV4: Soft-voting blend of calibrated models.
"""

from __future__ import annotations

import base64
import io
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression

from eldercare.fall_engine.features.features_v3 import TemporalFeaturesV3

FEATURE_NAMES_V4: list[str] = [
    "scale_norm_vel",
    "scale_norm_peak_vel",
    "norm_disp",
    "aspect_ratio",
    "aspect_rel_change",
    "torso_angle_deg",
    "torso_angle_change",
    "h_change_ratio",
    "low_posture_duration",
    "post_descent_stability",
    "avg_keypoint_confidence",
    "hip_height_ratio",
    "centroid_acceleration",
    "angular_velocity_deg_per_sec",
    "angular_acceleration",
    "floor_proximity_ratio",
    "cumulative_descent_distance",
    "velocity_direction_angle",
    "track_age_seconds",
    "track_gap_count",
    "max_gap_duration_seconds",
    "keypoint_availability_rate",
    "shoulder_width_ratio",
    "body_compactness",
]


class TemporalClassifierV4Base(ABC):
    """Abstract base class for V4 temporal fall classifiers."""

    @abstractmethod
    def predict_probability(self, features: Any) -> float:
        """Predict fall probability given a 24-dimensional feature vector or TemporalFeaturesV3."""

    @abstractmethod
    def predict_batch(self, features_batch: Any) -> list[float]:
        """Predict fall probabilities for a batch of feature vectors."""

    @abstractmethod
    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        """Return explainability contributions for input features."""

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> TemporalClassifierV4Base:
        """Load model from file."""

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """Serialize model to file."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the classifier architecture."""

    @property
    @abstractmethod
    def feature_dim(self) -> int:
        """Expected feature vector dimensionality (24)."""


@dataclass
class LogisticWeightsV4:
    feature_names: list[str]
    mean: list[float]
    scale: list[float]
    coefficients: list[float]
    intercept: float
    decision_threshold: float = 0.50
    regularization_strength: float = 1.0
    training_metadata: dict[str, Any] | None = None


class LogisticClassifierV4(TemporalClassifierV4Base):
    """L2-regularized logistic regression classifier with scale-normalized features."""

    def __init__(
        self,
        weights: LogisticWeightsV4 | None = None,
        l2_reg: float = 1.0,
        feature_dim: int = 24,
    ) -> None:
        self.weights = weights
        self.l2_reg = l2_reg
        self._feature_dim = feature_dim
        self._model_name = "LogisticClassifierV4"
        self._feature_names = list(FEATURE_NAMES_V4)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: list[str] | None = None,
        class_weight: str | dict[int, float] | None = "balanced",
    ) -> None:
        """Train L2 regularized logistic regression on features X and labels y."""
        if feature_names is not None:
            self._feature_names = feature_names

        mean = np.mean(X, axis=0)
        scale = np.std(X, axis=0)
        scale[scale < 1e-6] = 1.0

        X_norm = (X - mean) / scale

        c_val = 1.0 / self.l2_reg if self.l2_reg > 0 else 1.0
        model = LogisticRegression(
            penalty="l2",
            C=c_val,
            solver="lbfgs",
            class_weight=class_weight,
            max_iter=1000,
            random_state=42,
        )
        model.fit(X_norm, y)

        self.weights = LogisticWeightsV4(
            feature_names=self._feature_names,
            mean=mean.tolist(),
            scale=scale.tolist(),
            coefficients=model.coef_[0].tolist(),
            intercept=float(model.intercept_[0]),
            decision_threshold=0.50,
            regularization_strength=self.l2_reg,
            training_metadata={
                "samples": len(y),
                "positive_samples": int(np.sum(y == 1)),
                "negative_samples": int(np.sum(y == 0)),
            },
        )

    def _get_vector(self, features: Any) -> tuple[float, ...]:
        if isinstance(features, TemporalFeaturesV3):
            return features.feature_vector
        if isinstance(features, np.ndarray):
            return tuple(features.flatten().tolist())
        return tuple(features)

    def predict_probability(self, features: Any) -> float:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        raw_vec = self._get_vector(features)
        if len(raw_vec) != len(self.weights.coefficients):
            raise ValueError(
                f"Feature dimension mismatch: expected {len(self.weights.coefficients)}, got {len(raw_vec)}"
            )

        score = self.weights.intercept
        for x, m, s, w in zip(
            raw_vec, self.weights.mean, self.weights.scale, self.weights.coefficients
        ):
            norm_x = (x - m) / max(s, 1e-6)
            score += norm_x * w

        clamped = max(-30.0, min(30.0, score))
        return 1.0 / (1.0 + math.exp(-clamped))

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        raw_vec = self._get_vector(features)
        contributions: dict[str, float] = {}
        for name, x, m, s, w in zip(
            self.weights.feature_names,
            raw_vec,
            self.weights.mean,
            self.weights.scale,
            self.weights.coefficients,
        ):
            norm_x = (x - m) / max(s, 1e-6)
            contributions[name] = round(norm_x * w, 4)

        prob = self.predict_probability(features)
        return {
            "probability": prob,
            "intercept": self.weights.intercept,
            "contributions": contributions,
            "is_fall": prob >= self.weights.decision_threshold,
        }

    @classmethod
    def load(cls, path: str | Path) -> LogisticClassifierV4:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        weights = LogisticWeightsV4(
            feature_names=data["feature_names"],
            mean=data["mean"],
            scale=data["scale"],
            coefficients=data["coefficients"],
            intercept=data["intercept"],
            decision_threshold=data.get("decision_threshold", 0.50),
            regularization_strength=data.get("regularization_strength", 1.0),
            training_metadata=data.get("training_metadata"),
        )
        return cls(
            weights=weights,
            l2_reg=weights.regularization_strength,
            feature_dim=len(weights.feature_names),
        )

    def save(self, path: str | Path) -> None:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        data = {
            "schema_version": "4.0.0",
            "model_architecture": self.model_name,
            "feature_names": self.weights.feature_names,
            "mean": self.weights.mean,
            "scale": self.weights.scale,
            "coefficients": self.weights.coefficients,
            "intercept": self.weights.intercept,
            "decision_threshold": self.weights.decision_threshold,
            "regularization_strength": self.weights.regularization_strength,
            "training_metadata": self.weights.training_metadata,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


class FocalLoss(nn.Module):
    """Binary Focal Loss for class-imbalanced temporal classification."""

    def __init__(self, alpha: float = 0.75, gamma: float = 2.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce = F.binary_cross_entropy_with_logits(inputs, targets, reduction="none")
        pt = torch.exp(-bce)
        focal = self.alpha * (1 - pt) ** self.gamma * bce
        return focal.mean()


class MLPNetwork(nn.Module):
    """Feedforward Multi-Layer Perceptron for 24-dim temporal features."""

    def __init__(self, input_dim: int = 24, hidden_dim: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class MLPClassifierV4(TemporalClassifierV4Base):
    """PyTorch MLP classifier with standardization and focal loss."""

    def __init__(self, feature_dim: int = 24, hidden_dim: int = 64) -> None:
        self._feature_dim = feature_dim
        self._hidden_dim = hidden_dim
        self.model = MLPNetwork(feature_dim, hidden_dim)
        self.mean: list[float] = [0.0] * feature_dim
        self.scale: list[float] = [1.0] * feature_dim
        self.decision_threshold: float = 0.50
        self.training_metadata: dict[str, Any] | None = None
        self._feature_names = list(FEATURE_NAMES_V4)

    @property
    def model_name(self) -> str:
        return "MLPClassifierV4"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 25,
        lr: float = 0.003,
        batch_size: int = 32,
    ) -> None:
        # Compute standardization
        mean_arr = np.mean(X, axis=0)
        scale_arr = np.std(X, axis=0)
        scale_arr[scale_arr < 1e-6] = 1.0

        self.mean = mean_arr.tolist()
        self.scale = scale_arr.tolist()

        X_norm = (X - mean_arr) / scale_arr

        dataset = torch.utils.data.TensorDataset(
            torch.tensor(X_norm, dtype=torch.float32),
            torch.tensor(y, dtype=torch.float32),
        )
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        self.model.train()
        optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr, weight_decay=1e-4)
        criterion = FocalLoss(alpha=0.75, gamma=2.0)

        for _ in range(epochs):
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                out = self.model(batch_x)
                loss = criterion(out, batch_y)
                loss.backward()
                optimizer.step()

        self.training_metadata = {
            "samples": len(y),
            "positive_samples": int(np.sum(y == 1)),
            "negative_samples": int(np.sum(y == 0)),
            "epochs": epochs,
            "lr": lr,
        }

    def _get_vector(self, features: Any) -> list[float]:
        if isinstance(features, TemporalFeaturesV3):
            return list(features.feature_vector)
        if isinstance(features, np.ndarray):
            return features.flatten().tolist()
        return list(features)

    def predict_probability(self, features: Any) -> float:
        self.model.eval()
        raw_vec = self._get_vector(features)
        mean_arr = np.array(self.mean, dtype=np.float32)
        scale_arr = np.array(self.scale, dtype=np.float32)

        x_norm = (np.array(raw_vec, dtype=np.float32) - mean_arr) / np.maximum(scale_arr, 1e-6)
        x_tensor = torch.tensor(x_norm, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            logit = self.model(x_tensor)
            prob = torch.sigmoid(logit).item()
        return float(prob)

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        prob = self.predict_probability(features)
        return {
            "probability": prob,
            "is_fall": prob >= self.decision_threshold,
            "contributions": {},
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        buffer = io.BytesIO()
        torch.save(self.model.state_dict(), buffer)
        weights_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        data = {
            "schema_version": "4.0.0",
            "model_architecture": self.model_name,
            "feature_dim": self.feature_dim,
            "hidden_dim": self._hidden_dim,
            "feature_names": self._feature_names,
            "mean": self.mean,
            "scale": self.scale,
            "decision_threshold": self.decision_threshold,
            "training_metadata": self.training_metadata,
            "weights_state_dict_b64": weights_b64,
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> MLPClassifierV4:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        instance = cls(
            feature_dim=data.get("feature_dim", 24),
            hidden_dim=data.get("hidden_dim", 64),
        )
        instance.mean = data["mean"]
        instance.scale = data["scale"]
        instance.decision_threshold = data.get("decision_threshold", 0.50)
        instance.training_metadata = data.get("training_metadata")

        weights_bytes = base64.b64decode(data["weights_state_dict_b64"].encode("utf-8"))
        buffer = io.BytesIO(weights_bytes)
        state_dict = torch.load(buffer, weights_only=True)
        instance.model.load_state_dict(state_dict)
        return instance


class CausalConv1d(nn.Module):
    """Causal 1D convolution with left-padding to prevent temporal leakage."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int = 1,
    ) -> None:
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size,
            padding=self.padding,
            dilation=dilation,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        res = self.conv(x)
        if self.padding > 0:
            res = res[:, :, : -self.padding]
        return res


class TCNNetworkV4(nn.Module):
    """Temporal Convolutional Network for sliding window features."""

    def __init__(self, input_dim: int = 24, channels: int = 32) -> None:
        super().__init__()
        self.conv1 = CausalConv1d(input_dim, channels, kernel_size=3, dilation=1)
        self.conv2 = CausalConv1d(channels, channels * 2, kernel_size=3, dilation=2)
        self.fc = nn.Linear(channels * 2, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq, channels) -> (batch, channels, seq)
        x = x.transpose(1, 2)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        pooled = torch.mean(x, dim=2)
        return self.fc(pooled).squeeze(-1)


class TCNClassifierV4(TemporalClassifierV4Base):
    """TCN classifier with causal dilated convolutions."""

    def __init__(self, feature_dim: int = 24, channels: int = 32) -> None:
        self._feature_dim = feature_dim
        self._channels = channels
        self.model = TCNNetworkV4(feature_dim, channels)
        self.mean: list[float] = [0.0] * feature_dim
        self.scale: list[float] = [1.0] * feature_dim
        self.decision_threshold: float = 0.50
        self.training_metadata: dict[str, Any] | None = None
        self._feature_names = list(FEATURE_NAMES_V4)

    @property
    def model_name(self) -> str:
        return "TCNClassifierV4"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 20, lr: float = 0.002) -> None:
        mean_arr = np.mean(X, axis=0)
        scale_arr = np.std(X, axis=0)
        scale_arr[scale_arr < 1e-6] = 1.0

        self.mean = mean_arr.tolist()
        self.scale = scale_arr.tolist()

        X_norm = (X - mean_arr) / scale_arr
        if len(X_norm.shape) == 2:
            X_norm = np.expand_dims(X_norm, axis=1)

        X_t = torch.tensor(X_norm, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)

        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = FocalLoss(alpha=0.75, gamma=2.0)

        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)

        for _ in range(epochs):
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                out = self.model(batch_x)
                loss = criterion(out, batch_y)
                loss.backward()
                optimizer.step()

        self.training_metadata = {
            "samples": len(y),
            "positive_samples": int(np.sum(y == 1)),
            "epochs": epochs,
        }

    def _get_vector(self, features: Any) -> list[float]:
        if isinstance(features, TemporalFeaturesV3):
            return list(features.feature_vector)
        if isinstance(features, np.ndarray):
            return features.flatten().tolist()
        return list(features)

    def predict_probability(self, features: Any) -> float:
        self.model.eval()
        raw_vec = self._get_vector(features)
        mean_arr = np.array(self.mean, dtype=np.float32)
        scale_arr = np.array(self.scale, dtype=np.float32)

        x_norm = (np.array(raw_vec, dtype=np.float32) - mean_arr) / np.maximum(scale_arr, 1e-6)
        x_norm = x_norm.reshape(1, 1, -1)

        with torch.no_grad():
            out = self.model(torch.tensor(x_norm, dtype=torch.float32))
            prob = torch.sigmoid(out).item()
        return float(prob)

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.predict_probability(features)}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        torch.save(self.model.state_dict(), buffer)
        weights_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        data = {
            "schema_version": "4.0.0",
            "model_architecture": self.model_name,
            "feature_dim": self.feature_dim,
            "channels": self._channels,
            "feature_names": self._feature_names,
            "mean": self.mean,
            "scale": self.scale,
            "decision_threshold": self.decision_threshold,
            "training_metadata": self.training_metadata,
            "weights_state_dict_b64": weights_b64,
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> TCNClassifierV4:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        instance = cls(
            feature_dim=data.get("feature_dim", 24),
            channels=data.get("channels", 32),
        )
        instance.mean = data["mean"]
        instance.scale = data["scale"]
        instance.decision_threshold = data.get("decision_threshold", 0.50)
        instance.training_metadata = data.get("training_metadata")

        weights_bytes = base64.b64decode(data["weights_state_dict_b64"].encode("utf-8"))
        buffer = io.BytesIO(weights_bytes)
        state_dict = torch.load(buffer, weights_only=True)
        instance.model.load_state_dict(state_dict)
        return instance


class GRUNetworkV4(nn.Module):
    """GRU network for temporal sequence features."""

    def __init__(self, input_dim: int = 24, hidden_size: int = 32) -> None:
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, hn = self.gru(x)
        out = hn[-1]
        return self.fc(out).squeeze(-1)


class GRUClassifierV4(TemporalClassifierV4Base):
    """GRU classifier with recurrent state accumulation."""

    def __init__(self, feature_dim: int = 24, hidden_size: int = 32) -> None:
        self._feature_dim = feature_dim
        self._hidden_size = hidden_size
        self.model = GRUNetworkV4(feature_dim, hidden_size)
        self.mean: list[float] = [0.0] * feature_dim
        self.scale: list[float] = [1.0] * feature_dim
        self.decision_threshold: float = 0.50
        self.training_metadata: dict[str, Any] | None = None
        self._feature_names = list(FEATURE_NAMES_V4)

    @property
    def model_name(self) -> str:
        return "GRUClassifierV4"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 20, lr: float = 0.002) -> None:
        mean_arr = np.mean(X, axis=0)
        scale_arr = np.std(X, axis=0)
        scale_arr[scale_arr < 1e-6] = 1.0

        self.mean = mean_arr.tolist()
        self.scale = scale_arr.tolist()

        X_norm = (X - mean_arr) / scale_arr
        if len(X_norm.shape) == 2:
            X_norm = np.expand_dims(X_norm, axis=1)

        X_t = torch.tensor(X_norm, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)

        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = FocalLoss(alpha=0.75, gamma=2.0)

        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)

        for _ in range(epochs):
            for batch_x, batch_y in loader:
                optimizer.zero_grad()
                out = self.model(batch_x)
                loss = criterion(out, batch_y)
                loss.backward()
                optimizer.step()

        self.training_metadata = {
            "samples": len(y),
            "positive_samples": int(np.sum(y == 1)),
            "epochs": epochs,
        }

    def _get_vector(self, features: Any) -> list[float]:
        if isinstance(features, TemporalFeaturesV3):
            return list(features.feature_vector)
        if isinstance(features, np.ndarray):
            return features.flatten().tolist()
        return list(features)

    def predict_probability(self, features: Any) -> float:
        self.model.eval()
        raw_vec = self._get_vector(features)
        mean_arr = np.array(self.mean, dtype=np.float32)
        scale_arr = np.array(self.scale, dtype=np.float32)

        x_norm = (np.array(raw_vec, dtype=np.float32) - mean_arr) / np.maximum(scale_arr, 1e-6)
        x_norm = x_norm.reshape(1, 1, -1)

        with torch.no_grad():
            out = self.model(torch.tensor(x_norm, dtype=torch.float32))
            prob = torch.sigmoid(out).item()
        return float(prob)

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.predict_probability(features)}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        torch.save(self.model.state_dict(), buffer)
        weights_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        data = {
            "schema_version": "4.0.0",
            "model_architecture": self.model_name,
            "feature_dim": self.feature_dim,
            "hidden_size": self._hidden_size,
            "feature_names": self._feature_names,
            "mean": self.mean,
            "scale": self.scale,
            "decision_threshold": self.decision_threshold,
            "training_metadata": self.training_metadata,
            "weights_state_dict_b64": weights_b64,
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> GRUClassifierV4:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        instance = cls(
            feature_dim=data.get("feature_dim", 24),
            hidden_size=data.get("hidden_size", 32),
        )
        instance.mean = data["mean"]
        instance.scale = data["scale"]
        instance.decision_threshold = data.get("decision_threshold", 0.50)
        instance.training_metadata = data.get("training_metadata")

        weights_bytes = base64.b64decode(data["weights_state_dict_b64"].encode("utf-8"))
        buffer = io.BytesIO(weights_bytes)
        state_dict = torch.load(buffer, weights_only=True)
        instance.model.load_state_dict(state_dict)
        return instance


class EnsembleClassifierV4(TemporalClassifierV4Base):
    """Soft-voting ensemble of calibrated classifiers."""

    def __init__(
        self,
        classifiers: list[TemporalClassifierV4Base] | None = None,
        weights: list[float] | None = None,
        feature_dim: int = 24,
    ) -> None:
        self.classifiers = classifiers or []
        if weights is not None:
            total = sum(weights)
            self.weights = [w / total for w in weights]
        elif self.classifiers:
            n = len(self.classifiers)
            self.weights = [1.0 / n] * n
        else:
            self.weights = []
        self._feature_dim = feature_dim
        self.decision_threshold: float = 0.50

    @property
    def model_name(self) -> str:
        return "EnsembleClassifierV4"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def predict_probability(self, features: Any) -> float:
        if not self.classifiers:
            raise RuntimeError("Ensemble contains no classifiers.")
        probs = [clf.predict_probability(features) for clf in self.classifiers]
        ensemble_prob = sum(w * p for w, p in zip(self.weights, probs))
        return float(ensemble_prob)

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.predict_probability(features)}

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        models_data = []
        for i, clf in enumerate(self.classifiers):
            sub_path = p.parent / f"{p.stem}_member_{i}.json"
            clf.save(sub_path)
            models_data.append({
                "architecture": clf.model_name,
                "file": sub_path.name,
                "weight": self.weights[i],
            })

        data = {
            "schema_version": "4.0.0",
            "model_architecture": self.model_name,
            "feature_dim": self.feature_dim,
            "members": models_data,
            "decision_threshold": self.decision_threshold,
        }
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> EnsembleClassifierV4:
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        classifiers: list[TemporalClassifierV4Base] = []
        weights: list[float] = []

        arch_map = {
            "LogisticClassifierV4": LogisticClassifierV4,
            "MLPClassifierV4": MLPClassifierV4,
            "TCNClassifierV4": TCNClassifierV4,
            "GRUClassifierV4": GRUClassifierV4,
        }

        for m in data["members"]:
            arch_cls = arch_map.get(m["architecture"])
            if not arch_cls:
                raise ValueError(f"Unknown architecture: {m['architecture']}")
            sub_path = p.parent / m["file"]
            classifiers.append(arch_cls.load(sub_path))
            weights.append(m["weight"])

        instance = cls(
            classifiers=classifiers,
            weights=weights,
            feature_dim=data.get("feature_dim", 24),
        )
        instance.decision_threshold = data.get("decision_threshold", 0.50)
        return instance
