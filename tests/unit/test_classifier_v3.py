import tempfile
from pathlib import Path

import numpy as np

from eldercare.fall_engine.learned_classifier.classifier_v3 import (
    LogisticClassifierV3,
    LogisticWeightsV3,
)
from eldercare.fall_engine.learned_classifier.training_v3 import (
    ClassBalancer,
    CrossValidationBenchmark,
    SubjectDisjointSplitter,
)


def test_logistic_classifier_v3_predict():
    weights = LogisticWeightsV3(
        feature_names=[f"f_{i}" for i in range(24)],
        mean=[0.0] * 24,
        scale=[1.0] * 24,
        coefficients=[0.1] * 24,
        intercept=0.0,
    )
    clf = LogisticClassifierV3(weights=weights)
    prob = clf.predict_probability([1.0] * 24)
    assert 0.0 <= prob <= 1.0


def test_logistic_classifier_v3_save_load():
    weights = LogisticWeightsV3(
        feature_names=[f"f_{i}" for i in range(24)],
        mean=[0.0] * 24,
        scale=[1.0] * 24,
        coefficients=[0.1] * 24,
        intercept=0.0,
    )
    clf = LogisticClassifierV3(weights=weights)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "model.json"
        clf.save(path)
        loaded_clf = LogisticClassifierV3.load(path)
        assert loaded_clf.feature_dim == 24
        assert loaded_clf.weights.intercept == 0.0


def test_subject_disjoint_splitter():
    X = np.random.randn(100, 24)
    y = np.random.randint(0, 2, 100)
    groups = np.array([i // 10 for i in range(100)])  # 10 groups

    splitter = SubjectDisjointSplitter(n_splits=5)
    folds = splitter.split(X, y, groups)

    assert len(folds) == 5
    for train_idx, test_idx in folds:
        train_groups = set(groups[train_idx])
        test_groups = set(groups[test_idx])
        assert len(train_groups.intersection(test_groups)) == 0


def test_class_balancer():
    y = np.array([0, 0, 0, 1])
    weights = ClassBalancer.compute_class_weights(y)
    assert weights[1] > weights[0]


def test_cross_validation_benchmark():
    # Provide synthetic data such that classifier can get 100% metrics
    X = np.random.randn(100, 24)
    y = np.random.randint(0, 2, 100)
    # make it separable
    X[y == 1] += 5.0
    groups = np.array([i // 20 for i in range(100)])

    clf = LogisticClassifierV3(feature_dim=24)
    splitter = SubjectDisjointSplitter(n_splits=5)

    benchmark = CrossValidationBenchmark([clf], X, y, groups, splitter)
    result = benchmark.run()

    assert "results" in result
    assert clf.model_name in result["results"]
