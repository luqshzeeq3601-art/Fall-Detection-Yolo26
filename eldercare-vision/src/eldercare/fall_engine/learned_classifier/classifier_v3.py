"""Phase 11.6 v3 Temporal Classifier Base & Implementations."""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
import warnings

import numpy as np
try:
    from sklearn.linear_model import LogisticRegression
except ImportError:
    LogisticRegression = None
import torch
import torch.nn as nn
import torch.nn.functional as F

from eldercare.fall_engine.features.features_v3 import TemporalFeaturesV3


class TemporalClassifierV3Base(ABC):
    """Abstract base class for V3 temporal classifiers."""

    @abstractmethod
    def predict_probability(self, features: Any) -> float:
        pass

    @abstractmethod
    def predict_batch(self, features_batch: Any) -> list[float]:
        pass

    @abstractmethod
    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        pass

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> TemporalClassifierV3Base:
        pass

    @abstractmethod
    def save(self, path: str | Path) -> None:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def feature_dim(self) -> int:
        pass


@dataclass
class LogisticWeightsV3:
    feature_names: list[str]
    mean: list[float]
    scale: list[float]
    coefficients: list[float]
    intercept: float
    decision_threshold: float = 0.5
    regularization_strength: float = 1.0
    training_metadata: dict[str, Any] | None = None


class LogisticClassifierV3(TemporalClassifierV3Base):
    def __init__(
        self,
        weights: LogisticWeightsV3 | None = None,
        l2_reg: float = 1.0,
        feature_dim: int = 24
    ) -> None:
        self.weights = weights
        self.l2_reg = l2_reg
        self._feature_dim = feature_dim
        self._model_name = "LogisticClassifierV3"
        self._feature_names = [f"f_{i}" for i in range(feature_dim)]

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(self, X: np.ndarray, y: np.ndarray, feature_names: list[str] | None = None) -> None:
        if LogisticRegression is None:
            raise RuntimeError("sklearn is required for training LogisticClassifierV3")
        
        if feature_names is not None:
            self._feature_names = feature_names

        # Standardization
        mean = np.mean(X, axis=0)
        scale = np.std(X, axis=0)
        scale[scale == 0] = 1.0
        
        X_norm = (X - mean) / scale
        
        C = 1.0 / self.l2_reg if self.l2_reg > 0 else 1.0
        model = LogisticRegression(penalty='l2', C=C, solver='lbfgs')
        model.fit(X_norm, y)
        
        self.weights = LogisticWeightsV3(
            feature_names=self._feature_names,
            mean=mean.tolist(),
            scale=scale.tolist(),
            coefficients=model.coef_[0].tolist(),
            intercept=float(model.intercept_[0]),
            decision_threshold=0.5,
            regularization_strength=self.l2_reg,
            training_metadata={"samples": len(y)}
        )

    def _get_vector(self, features: Any) -> tuple[float, ...]:
        if isinstance(features, TemporalFeaturesV3):
            return features.feature_vector
        return tuple(features)

    def predict_probability(self, features: Any) -> float:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        raw_vec = self._get_vector(features)
        
        score = self.weights.intercept
        for x, m, s, w in zip(raw_vec, self.weights.mean, self.weights.scale, self.weights.coefficients):
            norm_x = (x - m) / max(s, 1e-6)
            score += norm_x * w
            
        clamped_score = max(-30.0, min(30.0, score))
        return 1.0 / (1.0 + math.exp(-clamped_score))

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        raw_vec = self._get_vector(features)
        
        contributions = {}
        for name, x, m, s, w in zip(self.weights.feature_names, raw_vec, self.weights.mean, self.weights.scale, self.weights.coefficients):
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
    def load(cls, path: str | Path) -> LogisticClassifierV3:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        weights = LogisticWeightsV3(
            feature_names=data["feature_names"],
            mean=data["mean"],
            scale=data["scale"],
            coefficients=data["coefficients"],
            intercept=data["intercept"],
            decision_threshold=data.get("decision_threshold", 0.5),
            regularization_strength=data.get("regularization_strength", 1.0),
            training_metadata=data.get("training_metadata")
        )
        return cls(weights=weights, l2_reg=weights.regularization_strength, feature_dim=len(weights.feature_names))

    def save(self, path: str | Path) -> None:
        if not self.weights:
            raise RuntimeError("Model not trained or loaded.")
        data = {
            "schema_version": "3.0.0",
            "feature_names": self.weights.feature_names,
            "mean": self.weights.mean,
            "scale": self.weights.scale,
            "coefficients": self.weights.coefficients,
            "intercept": self.weights.intercept,
            "decision_threshold": self.weights.decision_threshold,
            "regularization_strength": self.weights.regularization_strength,
            "training_metadata": self.weights.training_metadata
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")


class FocalLoss(nn.Module):
    def __init__(self, alpha: float = 1.0, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = F.binary_cross_entropy_with_logits(inputs, targets, reduction='none')
        pt = torch.exp(-bce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * bce_loss
        return focal_loss.mean()


class CausalConv1d(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, dilation=1):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(in_channels, out_channels, kernel_size, padding=self.padding, dilation=dilation)

    def forward(self, x):
        res = self.conv(x)
        if self.padding > 0:
            res = res[:, :, :-self.padding]
        return res


class TCNNetwork(nn.Module):
    def __init__(self, input_dim: int = 24):
        super().__init__()
        self.conv1 = CausalConv1d(input_dim, 32, kernel_size=3)
        self.conv2 = CausalConv1d(32, 64, kernel_size=3)
        self.fc = nn.Linear(64, 1)

    def forward(self, x):
        # x: (batch, seq, features)
        x = x.transpose(1, 2) # (batch, features, seq)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = torch.mean(x, dim=2) # global average pooling
        return self.fc(x).squeeze(-1)


class TCNClassifierV3(TemporalClassifierV3Base):
    def __init__(self, feature_dim: int = 24):
        self._feature_dim = feature_dim
        self.model = TCNNetwork(feature_dim)
        self._decision_threshold = 0.5
        
    @property
    def model_name(self) -> str:
        return "TCNClassifierV3"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 10, use_focal_loss: bool = True, class_weights: list[float] | None = None) -> None:
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        
        # X shape: (batch, seq, feature)
        # For simplicity, if 2D, make it 3D (seq=1)
        if len(X.shape) == 2:
            X = np.expand_dims(X, axis=1)
            
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)

        criterion = FocalLoss() if use_focal_loss else nn.BCEWithLogitsLoss(pos_weight=torch.tensor(class_weights[1]/class_weights[0]) if class_weights else None)

        for _ in range(epochs):
            optimizer.zero_grad()
            out = self.model(X_t)
            loss = criterion(out, y_t)
            loss.backward()
            optimizer.step()

    def predict_probability(self, features: Any) -> float:
        self.model.eval()
        if isinstance(features, TemporalFeaturesV3):
            vec = features.feature_vector
        else:
            vec = features
            
        x = np.array(vec)
        if len(x.shape) == 1:
            x = x.reshape(1, 1, -1)
        elif len(x.shape) == 2:
            x = x.reshape(1, x.shape[0], x.shape[1])
            
        with torch.no_grad():
            out = self.model(torch.tensor(x, dtype=torch.float32))
            prob = torch.sigmoid(out).item()
        return prob

    def predict_batch(self, features_batch: Any) -> list[float]:
        self.model.eval()
        # Assume list of 2D or list of 1D
        probs = []
        for f in features_batch:
            probs.append(self.predict_probability(f))
        return probs

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.predict_probability(features)}

    @classmethod
    def load(cls, path: str | Path) -> TCNClassifierV3:
        p = Path(path)
        config_path = p.with_suffix('.json')
        config = json.loads(config_path.read_text(encoding="utf-8"))
        instance = cls(feature_dim=config["feature_dim"])
        instance.model.load_state_dict(torch.load(p, weights_only=True))
        return instance

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), p)
        config = {
            "schema_version": "3.0.0",
            "feature_dim": self.feature_dim,
            "decision_threshold": self._decision_threshold
        }
        p.with_suffix('.json').write_text(json.dumps(config, indent=2), encoding="utf-8")


class GRUNetwork(nn.Module):
    def __init__(self, input_dim: int = 24, hidden_size: int = 32, num_layers: int = 1):
        super().__init__()
        self.gru = nn.GRU(input_dim, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        _, hn = self.gru(x)
        out = hn[-1] # last layer hidden state
        return self.fc(out).squeeze(-1)


class GRUClassifierV3(TemporalClassifierV3Base):
    def __init__(self, feature_dim: int = 24):
        self._feature_dim = feature_dim
        self.model = GRUNetwork(feature_dim)
        self._decision_threshold = 0.5
        
    @property
    def model_name(self) -> str:
        return "GRUClassifierV3"

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 10, use_focal_loss: bool = True) -> None:
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        
        if len(X.shape) == 2:
            X = np.expand_dims(X, axis=1)
            
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32)

        criterion = FocalLoss() if use_focal_loss else nn.BCEWithLogitsLoss()

        for _ in range(epochs):
            optimizer.zero_grad()
            out = self.model(X_t)
            loss = criterion(out, y_t)
            loss.backward()
            optimizer.step()

    def predict_probability(self, features: Any) -> float:
        self.model.eval()
        if isinstance(features, TemporalFeaturesV3):
            vec = features.feature_vector
        else:
            vec = features
            
        x = np.array(vec)
        if len(x.shape) == 1:
            x = x.reshape(1, 1, -1)
        elif len(x.shape) == 2:
            x = x.reshape(1, x.shape[0], x.shape[1])
            
        with torch.no_grad():
            out = self.model(torch.tensor(x, dtype=torch.float32))
            prob = torch.sigmoid(out).item()
        return prob

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.predict_probability(f) for f in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.predict_probability(features)}

    @classmethod
    def load(cls, path: str | Path) -> GRUClassifierV3:
        p = Path(path)
        config_path = p.with_suffix('.json')
        config = json.loads(config_path.read_text(encoding="utf-8"))
        instance = cls(feature_dim=config["feature_dim"])
        instance.model.load_state_dict(torch.load(p, weights_only=True))
        return instance

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self.model.state_dict(), p)
        config = {
            "schema_version": "3.0.0",
            "feature_dim": self.feature_dim,
            "decision_threshold": self._decision_threshold
        }
        p.with_suffix('.json').write_text(json.dumps(config, indent=2), encoding="utf-8")
