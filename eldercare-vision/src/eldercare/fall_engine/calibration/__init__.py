"""Threshold calibration and development set evaluation package (P4-007)."""

from eldercare.fall_engine.calibration.config_loader import (
    load_fall_detection_config,
)
from eldercare.fall_engine.calibration.evaluator import (
    CalibrationReport,
    DevelopmentSetCalibrationEvaluator,
)
from eldercare.fall_engine.calibration.freeze import (
    FROZEN_ARTIFACT_DIGESTS,
    assert_frozen_artifacts_intact,
    compute_file_sha256,
    verify_frozen_artifacts,
)

__all__ = [
    "FROZEN_ARTIFACT_DIGESTS",
    "CalibrationReport",
    "DevelopmentSetCalibrationEvaluator",
    "assert_frozen_artifacts_intact",
    "compute_file_sha256",
    "load_fall_detection_config",
    "verify_frozen_artifacts",
]
