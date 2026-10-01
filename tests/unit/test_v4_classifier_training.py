# ruff: noqa: N803, N806, N812, B905, E501
"""Unit tests for Phase 11.7 V4 Temporal Classifier and Training Framework."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
)
from eldercare.fall_engine.learned_classifier.classifier_v4 import (
    FEATURE_NAMES_V4,
    EnsembleClassifierV4,
    GRUClassifierV4,
    LogisticClassifierV4,
    MLPClassifierV4,
    TCNClassifierV4,
)
from eldercare.fall_engine.learned_classifier.training_v4 import (
    ClassBalancer,
    CrossValidationBenchmarkV4,
    SubjectDisjointSplitter,
    ThresholdCalibratorV4,
)


def _generate_synthetic_pose_dataset(
    n_samples: int = 120,
    n_subjects: int = 6,
    feature_dim: int = 24,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate toy dataset for testing classifiers and split isolation."""
    rng = np.random.default_rng(random_state)
    subjects = [f"subj-0{i + 1}" for i in range(n_subjects)]
    groups = rng.choice(subjects, size=n_samples)

    # Class 0: low velocity, upright posture
    # Class 1: high velocity, low posture
    y = rng.choice([0, 1], size=n_samples, p=[0.7, 0.3])
    X = np.zeros((n_samples, feature_dim), dtype=np.float32)

    for i in range(n_samples):
        if y[i] == 1:
            X[i, 0] = rng.uniform(0.3, 1.2)  # scale_norm_vel
            X[i, 1] = rng.uniform(0.5, 2.0)  # scale_norm_peak_vel
            X[i, 15] = rng.uniform(0.0, 0.2)  # floor_proximity_ratio
        else:
            X[i, 0] = rng.uniform(-0.1, 0.2)
            X[i, 1] = rng.uniform(0.0, 0.4)
            X[i, 15] = rng.uniform(0.3, 0.9)
        # Add random noise to other features
        X[i, 2:] = rng.normal(0.0, 1.0, size=feature_dim - 2)

    return X, y, groups


def test_feature_names_integrity() -> None:
    """Verify feature vector names length and uniqueness."""
    assert len(FEATURE_NAMES_V4) == 24
    assert len(set(FEATURE_NAMES_V4)) == 24
    assert "scale_norm_vel" in FEATURE_NAMES_V4
    assert "floor_proximity_ratio" in FEATURE_NAMES_V4


def test_training_isolation_enforcement() -> None:
    """Verify holdout access errors are strictly raised on forbidden splits."""
    DatasetSplitGuard.enforce_training_isolation("dev")
    DatasetSplitGuard.enforce_training_isolation("train")

    with pytest.raises(HoldoutAccessError):
        DatasetSplitGuard.enforce_training_isolation("holdout")

    with pytest.raises(HoldoutAccessError):
        DatasetSplitGuard.enforce_training_isolation("test")


def test_subject_disjoint_splitter() -> None:
    """Verify 5-fold cross-validation partition enforces zero subject overlap."""
    X, y, groups = _generate_synthetic_pose_dataset(n_samples=100, n_subjects=6)
    splitter = SubjectDisjointSplitter(n_splits=5, random_state=42)
    folds = splitter.split(X, y, groups)

    assert len(folds) == 5
    for train_idx, val_idx in folds:
        train_subjs = set(groups[train_idx])
        val_subjs = set(groups[val_idx])
        overlap = train_subjs & val_subjs
        assert len(overlap) == 0, f"Leaked subjects: {overlap}"
        assert len(train_subjs) > 0
        assert len(val_subjs) > 0

    # Test error when subjects < folds
    with pytest.raises(ValueError):
        splitter.split(X, y, groups=np.array(["subj-01"] * len(y)))


def test_class_balancer() -> None:
    """Verify class balance computation and resampling."""
    y = np.array([0, 0, 0, 0, 1])
    weights = ClassBalancer.compute_class_weights(y)
    assert weights[1] > weights[0]
    assert weights[0] == pytest.approx(5 / (2 * 4))
    assert weights[1] == pytest.approx(5 / (2 * 1))

    X = np.ones((5, 24))
    X_bal, y_bal, _ = ClassBalancer.balanced_sample(X, y)
    assert np.sum(y_bal == 0) == np.sum(y_bal == 1) == 4


def test_logistic_classifier_v4(tmp_path: Path) -> None:
    """Verify LogisticClassifierV4 training, prediction, explainability, and serialization."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=80)
    clf = LogisticClassifierV4(l2_reg=1.0)
    clf.train(X, y)

    # Predictions
    p = clf.predict_probability(X[0])
    assert 0.0 <= p <= 1.0

    batch_p = clf.predict_batch(X[:5])
    assert len(batch_p) == 5
    assert all(0.0 <= prob <= 1.0 for prob in batch_p)

    # Feature contributions
    contribs = clf.get_feature_contributions(X[0])
    assert "probability" in contribs
    assert "contributions" in contribs
    assert len(contribs["contributions"]) == 24

    # Serialization roundtrip
    save_file = tmp_path / "logistic_v4.json"
    clf.save(save_file)
    assert save_file.is_file()

    loaded = LogisticClassifierV4.load(save_file)
    assert loaded.model_name == "LogisticClassifierV4"
    p_loaded = loaded.predict_probability(X[0])
    assert p == pytest.approx(p_loaded, rel=1e-5)


def test_mlp_classifier_v4(tmp_path: Path) -> None:
    """Verify MLPClassifierV4 training, prediction, and serialization."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=60)
    clf = MLPClassifierV4(feature_dim=24, hidden_dim=32)
    clf.train(X, y, epochs=5, batch_size=16)

    p = clf.predict_probability(X[0])
    assert 0.0 <= p <= 1.0

    batch_p = clf.predict_batch(X[:3])
    assert len(batch_p) == 3

    save_file = tmp_path / "mlp_v4.json"
    clf.save(save_file)
    assert save_file.is_file()

    loaded = MLPClassifierV4.load(save_file)
    assert loaded.model_name == "MLPClassifierV4"
    p_loaded = loaded.predict_probability(X[0])
    assert p == pytest.approx(p_loaded, rel=1e-5)


def test_tcn_classifier_v4(tmp_path: Path) -> None:
    """Verify TCNClassifierV4 training, prediction, and serialization."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=50)
    clf = TCNClassifierV4(feature_dim=24, channels=16)
    clf.train(X, y, epochs=3)

    p = clf.predict_probability(X[0])
    assert 0.0 <= p <= 1.0

    save_file = tmp_path / "tcn_v4.json"
    clf.save(save_file)
    loaded = TCNClassifierV4.load(save_file)
    assert loaded.model_name == "TCNClassifierV4"
    assert p == pytest.approx(loaded.predict_probability(X[0]), rel=1e-5)


def test_gru_classifier_v4(tmp_path: Path) -> None:
    """Verify GRUClassifierV4 training, prediction, and serialization."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=50)
    clf = GRUClassifierV4(feature_dim=24, hidden_size=16)
    clf.train(X, y, epochs=3)

    p = clf.predict_probability(X[0])
    assert 0.0 <= p <= 1.0

    save_file = tmp_path / "gru_v4.json"
    clf.save(save_file)
    loaded = GRUClassifierV4.load(save_file)
    assert loaded.model_name == "GRUClassifierV4"
    assert p == pytest.approx(loaded.predict_probability(X[0]), rel=1e-5)


def test_ensemble_classifier_v4(tmp_path: Path) -> None:
    """Verify EnsembleClassifierV4 soft-voting blend and serialization."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=50)
    c1 = LogisticClassifierV4()
    c1.train(X, y)
    c2 = MLPClassifierV4(feature_dim=24, hidden_dim=16)
    c2.train(X, y, epochs=2)

    ensemble = EnsembleClassifierV4(classifiers=[c1, c2], weights=[0.6, 0.4])
    p1 = c1.predict_probability(X[0])
    p2 = c2.predict_probability(X[0])
    p_ens = ensemble.predict_probability(X[0])
    assert p_ens == pytest.approx(0.6 * p1 + 0.4 * p2, rel=1e-5)

    save_file = tmp_path / "ensemble_v4.json"
    ensemble.save(save_file)
    loaded = EnsembleClassifierV4.load(save_file)
    assert loaded.model_name == "EnsembleClassifierV4"
    assert p_ens == pytest.approx(loaded.predict_probability(X[0]), rel=1e-5)


def test_cv_benchmark_v4_selection() -> None:
    """Verify CrossValidationBenchmarkV4 runs subject-disjoint folds and selects winner."""
    X, y, groups = _generate_synthetic_pose_dataset(n_samples=100, n_subjects=6)
    factories = {
        "Logistic": lambda: LogisticClassifierV4(l2_reg=1.0),
        "MLP": lambda: MLPClassifierV4(feature_dim=24, hidden_dim=16),
    }

    benchmark = CrossValidationBenchmarkV4(
        classifier_factories=factories,
        X=X,
        y=y,
        groups=groups,
        decision_threshold=0.50,
    )
    results = benchmark.run()
    assert "leaderboard" in results
    assert "winner" in results
    assert results["winner"] in ["Logistic", "MLP"]
    assert "winning_f2" in results
    assert results["winning_f2"] >= 0.0


def test_threshold_calibrator_v4() -> None:
    """Verify threshold calibrator returns valid threshold and metrics."""
    X, y, _ = _generate_synthetic_pose_dataset(n_samples=60)
    clf = LogisticClassifierV4()
    clf.train(X, y)

    calib = ThresholdCalibratorV4.calibrate(clf, X, y, target_recall=0.85)
    assert "threshold" in calib
    assert 0.10 <= calib["threshold"] <= 0.90
    assert 0.0 <= calib["recall"] <= 1.0
    assert 0.0 <= calib["f2"] <= 1.0
