"""Unit tests for threshold calibration config loader and dev evaluator (P4-007)."""

from __future__ import annotations

from pathlib import Path

import pytest

from eldercare.fall_engine.calibration.config_loader import load_fall_detection_config
from eldercare.fall_engine.calibration.evaluator import (
    DevelopmentSetCalibrationEvaluator,
)
from eldercare.fall_engine.confidence.calculator import FallConfidenceConfig
from eldercare.fall_engine.confidence.cooldown import CooldownConfig
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.state_machine.config import FallStateMachineConfig
from tests.fixtures.synthetic_fall_fixtures import (
    generate_fall_sequence,
    generate_walking_sequence,
)


@pytest.fixture
def config_file() -> Path:
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "fall_detection.yaml"
    assert config_path.is_file(), f"Config file not found at {config_path}"
    return config_path


class TestFallDetectionConfigLoader:
    """Test YAML config loading and validation."""

    def test_load_production_config(self, config_file: Path) -> None:
        state_cfg, conf_cfg, cd_cfg = load_fall_detection_config(config_file)

        assert isinstance(state_cfg, FallStateMachineConfig)
        assert isinstance(conf_cfg, FallConfidenceConfig)
        assert isinstance(cd_cfg, CooldownConfig)

        # Verify calibrated values from AI_SPEC §8 & §9
        assert state_cfg.feature_window_sec == 0.5
        assert state_cfg.descent_velocity_threshold == 0.5
        assert state_cfg.peak_descent_velocity_threshold == 1.0
        assert state_cfg.fallen_aspect_ratio_max == 1.0
        assert state_cfg.fallen_torso_angle_max_deg == 40.0
        assert state_cfg.down_confirmation_sec == 1.0

        assert conf_cfg.weight_motion == 0.35
        assert conf_cfg.weight_posture == 0.35
        assert conf_cfg.weight_persistence == 0.30
        assert conf_cfg.min_confidence_to_confirm == 0.40

        assert cd_cfg.incident_cooldown_sec == 5.0
        assert cd_cfg.camera_cooldown_sec == 0.5

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_fall_detection_config(tmp_path / "missing.yaml")

    def test_reject_invalid_yaml(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("fall_engine: [unclosed list", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_fall_detection_config(bad_yaml)

    def test_reject_weights_not_summing_to_one(self, tmp_path: Path) -> None:
        bad_weights = tmp_path / "bad_weights.yaml"
        bad_weights.write_text(
            """
fall_engine: {}
confidence:
  weight_motion: 0.5
  weight_posture: 0.5
  weight_persistence: 0.5
cooldown: {}
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="weights must sum to 1.0"):
            load_fall_detection_config(bad_weights)


class TestDevelopmentSetCalibrationEvaluator:
    """Test dev-split evaluation and anti-leakage protection."""

    def test_anti_leakage_guard_rejects_test_split(self) -> None:
        evaluator = DevelopmentSetCalibrationEvaluator()
        test_record = SequenceManifestRecord(
            sample_id="test-fall-01",
            source_dataset="URFD",
            sequence_id="fall-01",
            subject_id="sub-1",
            camera_id="cam-01",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="",
            split="test",  # FORBIDDEN for calibration
            license="CC-BY-4.0",
            notes="",
        )
        test_obs = generate_fall_sequence(duration_sec=2.0, fps=15.0)

        with pytest.raises(ValueError, match="Data leakage detected"):
            evaluator.evaluate_dev_sequences([(test_record, test_obs, 1.0)])

    def test_evaluator_produces_calibration_report(self) -> None:
        evaluator = DevelopmentSetCalibrationEvaluator()
        dev_fall = SequenceManifestRecord(
            sample_id="dev-fall-01",
            source_dataset="URFD",
            sequence_id="fall-01",
            subject_id="sub-1",
            camera_id="cam-01",
            activity="fall",
            is_fall=True,
            fall_type="slip",
            path_local="",
            split="dev",
            license="CC-BY-4.0",
            notes="",
        )
        dev_adl = SequenceManifestRecord(
            sample_id="dev-adl-01",
            source_dataset="URFD",
            sequence_id="adl-01",
            subject_id="sub-1",
            camera_id="cam-01",
            activity="walking",
            is_fall=False,
            fall_type="none",
            path_local="",
            split="dev",
            license="CC-BY-4.0",
            notes="",
        )
        fall_obs = generate_fall_sequence(duration_sec=3.0, fps=15.0, fall_start_sec=0.5)
        adl_obs = generate_walking_sequence(duration_sec=3.0, fps=15.0)

        report, results = evaluator.evaluate_dev_sequences(
            [
                (dev_fall, fall_obs, 0.5),
                (dev_adl, adl_obs, None),
            ]
        )

        assert report.metrics.total_sequences == 2
        assert report.metrics.tp == 1
        assert report.metrics.tn == 1
        assert report.metrics.fp == 0
        assert report.metrics.fn == 0
        assert report.adl_rejection_rate == 1.0
        assert report.fall_detection_rate == 1.0
        assert report.meets_targets is True
        assert "walking" in report.activity_breakdown
        assert "fall" in report.activity_breakdown
