# ruff: noqa: N803, N806, E501
"""Unit tests for Phase 11.7 V4 Fall Detection Threshold Calibration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from eldercare.fall_engine.calibration.calibrator_v4 import (
    CalibrationPoint,
    OperatingCurveSummary,
    ThresholdCalibratorEngineV4,
    ThresholdTriplet,
)
from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
)


def test_threshold_triplet_validation() -> None:
    """Verify validation constraints on threshold triplet ordering."""
    valid = ThresholdTriplet(
        veto_threshold=0.25,
        trigger_threshold=0.40,
        confirmation_threshold=0.55,
        sensitivity=0.92,
        specificity=0.94,
        f1_score=0.90,
        f2_score=0.91,
    )
    valid.validate()

    # Invalid: veto > trigger
    with pytest.raises(ValueError):
        ThresholdTriplet(
            veto_threshold=0.50,
            trigger_threshold=0.40,
            confirmation_threshold=0.55,
            sensitivity=0.92,
            specificity=0.94,
            f1_score=0.90,
            f2_score=0.91,
        ).validate()

    # Invalid: trigger > confirm
    with pytest.raises(ValueError):
        ThresholdTriplet(
            veto_threshold=0.25,
            trigger_threshold=0.60,
            confirmation_threshold=0.55,
            sensitivity=0.92,
            specificity=0.94,
            f1_score=0.90,
            f2_score=0.91,
        ).validate()

    # Invalid: threshold <= 0.0 or >= 1.0
    with pytest.raises(ValueError):
        ThresholdTriplet(
            veto_threshold=0.0,
            trigger_threshold=0.40,
            confirmation_threshold=0.55,
            sensitivity=0.92,
            specificity=0.94,
            f1_score=0.90,
            f2_score=0.91,
        ).validate()


def test_operating_curves_computation() -> None:
    """Verify computation of PR, ROC, and F-beta operating curves."""
    rng = np.random.default_rng(42)
    y_true = np.array([1] * 50 + [0] * 150)
    # Give positives higher probabilities on average
    y_probs = np.concatenate(
        [
            rng.uniform(0.6, 0.95, size=50),
            rng.uniform(0.05, 0.45, size=150),
        ]
    )

    summary = ThresholdCalibratorEngineV4.compute_curves(y_true, y_probs, n_points=51)

    assert isinstance(summary, OperatingCurveSummary)
    assert len(summary.points) == 51
    assert 0.90 <= summary.auc_roc <= 1.0
    assert 0.80 <= summary.auc_pr <= 1.0
    assert 0.0 < summary.best_f1_threshold < 1.0
    assert 0.0 < summary.best_f2_threshold < 1.0
    assert 0.0 < summary.high_sensitivity_threshold < 1.0
    assert 0.0 < summary.high_specificity_threshold < 1.0

    for pt in summary.points:
        assert isinstance(pt, CalibrationPoint)
        assert 0.0 <= pt.tpr <= 1.0
        assert 0.0 <= pt.fpr <= 1.0
        assert 0.0 <= pt.precision <= 1.0
        assert 0.0 <= pt.recall <= 1.0
        assert 0.0 <= pt.specificity <= 1.0


def test_find_optimal_triplet() -> None:
    """Verify automatic search for operational threshold triplet."""
    rng = np.random.default_rng(42)
    y_true = np.array([1] * 40 + [0] * 160)
    y_probs = np.concatenate(
        [
            rng.uniform(0.55, 0.90, size=40),
            rng.uniform(0.10, 0.40, size=160),
        ]
    )

    triplet = ThresholdCalibratorEngineV4.find_optimal_triplet(
        y_true, y_probs, target_sensitivity=0.90, min_specificity=0.90
    )
    triplet.validate()

    assert triplet.veto_threshold <= triplet.trigger_threshold <= triplet.confirmation_threshold
    assert triplet.sensitivity >= 0.85
    assert triplet.specificity >= 0.85
    assert 0.0 <= triplet.f1_score <= 1.0
    assert 0.0 <= triplet.f2_score <= 1.0


def test_generate_v4_yaml_config(tmp_path: Path) -> None:
    """Verify emission of validated config/fall_detection_v4.yaml."""
    base_yaml = tmp_path / "base.yaml"
    base_data = {
        "fall_engine_v3": {
            "feature_window_sec": 1.0,
            "descent_velocity_threshold": 0.35,
        },
        "learned_classifier": {
            "enabled": True,
            "model_type": "logistic",
            "trigger_threshold": 0.50,
        },
        "models": {
            "config_version": "3.0.0",
        },
    }
    base_yaml.write_text(yaml.dump(base_data), encoding="utf-8")

    triplet = ThresholdTriplet(
        veto_threshold=0.20,
        trigger_threshold=0.35,
        confirmation_threshold=0.50,
        sensitivity=0.95,
        specificity=0.96,
        f1_score=0.92,
        f2_score=0.94,
    )

    out_yaml = tmp_path / "fall_detection_v4.yaml"
    ThresholdCalibratorEngineV4.generate_v4_yaml_config(
        triplet=triplet,
        base_yaml_path=base_yaml,
        output_yaml_path=out_yaml,
    )

    assert out_yaml.is_file()
    cfg = yaml.safe_load(out_yaml.read_text(encoding="utf-8"))

    assert "fall_engine_v4" in cfg
    assert cfg["fall_engine_v4"]["feature_schema_version"] == "4.0.0"
    assert cfg["learned_classifier"]["trigger_threshold"] == 0.35
    assert cfg["learned_classifier"]["confirmation_threshold"] == 0.50
    assert cfg["learned_classifier"]["veto_threshold"] == 0.20
    assert (
        cfg["learned_classifier"]["model_weights_path"] == "models/temporal_fall_classifier_v4.json"
    )
    assert cfg["models"]["config_version"] == "4.0.0"


def test_calibration_isolation_enforcement() -> None:
    """Verify calibration runner strictly rejects test or holdout splits."""
    DatasetSplitGuard.enforce_training_isolation("dev", context="Calibration")

    with pytest.raises(HoldoutAccessError):
        DatasetSplitGuard.enforce_training_isolation("test", context="Calibration")

    with pytest.raises(HoldoutAccessError):
        DatasetSplitGuard.enforce_training_isolation("holdout", context="Calibration")
