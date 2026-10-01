"""P11.7-005 — Verification tests for wiring fixes W1–W6."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eldercare.fall_engine.features.features_v3 import (
    extract_temporal_features_v3,
)
from eldercare.fall_engine.learned_classifier.classifier_v3 import (
    LogisticClassifierV3,
    LogisticWeightsV3,
    TemporalClassifierV3Base,
)
from eldercare.fall_engine.state_machine.states import FallState
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import (
    FallStateMachineManagerV3,
    TrackFallStateMachineV3,
    _get_default_v3_classifier,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

ROOT = Path(__file__).resolve().parents[2]


def _make_observation(
    timestamp: float,
    y_center: float = 50.0,
    bbox_h: float = 100.0,
    bbox_w: float = 30.0,
    is_down: bool = False,
    track_id: int = 1,
) -> TrackObservation:
    """Create synthetic TrackObservation for testing."""
    x_center = 50.0
    x1, y1 = x_center - bbox_w / 2, y_center - bbox_h / 2
    x2, y2 = x_center + bbox_w / 2, y_center + bbox_h / 2
    img_h = 100 if is_down else 480

    kpts = []
    for _ in range(17):
        kpts.append(Keypoint(present=True, x=x_center, y=y_center, confidence=0.9))

    if is_down:
        kpts[5] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9)
        kpts[6] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9)
        kpts[11] = Keypoint(present=True, x=x2, y=y2, confidence=0.9)
        kpts[12] = Keypoint(present=True, x=x2, y=y2, confidence=0.9)
    else:
        kpts[5] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9)
        kpts[6] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9)
        kpts[11] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9)
        kpts[12] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9)

    return TrackObservation(
        camera_id="cam1",
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=(x1, y1, x2, y2),
        keypoints=tuple(kpts),
        image_width=640,
        image_height=img_h,
        detection_confidence=0.9,
    )


class DummyMockClassifier(TemporalClassifierV3Base):
    """Mock classifier for deterministically testing veto / confirmation."""

    def __init__(self, fixed_prob: float = 0.5) -> None:
        self.fixed_prob = fixed_prob

    def predict_probability(self, features: Any) -> float:
        return self.fixed_prob

    def predict_batch(self, features_batch: Any) -> list[float]:
        return [self.fixed_prob for _ in features_batch]

    def get_feature_contributions(self, features: Any) -> dict[str, Any]:
        return {"probability": self.fixed_prob, "is_fall": self.fixed_prob >= 0.5}

    @classmethod
    def load(cls, path: str | Path) -> DummyMockClassifier:
        return cls()

    def save(self, path: str | Path) -> None:
        pass

    @property
    def model_name(self) -> str:
        return "DummyMockClassifier"

    @property
    def feature_dim(self) -> int:
        return 24


def test_w1_feature_dimension_validation() -> None:
    """W1: Ensure dimension mismatch is rejected and 24-feature vector is validated."""
    weights = LogisticWeightsV3(
        feature_names=[f"f_{i}" for i in range(24)],
        mean=[0.0] * 24,
        scale=[1.0] * 24,
        coefficients=[0.5] * 24,
        intercept=0.0,
    )
    clf = LogisticClassifierV3(weights=weights, feature_dim=24)

    # 12-feature slice should raise ValueError, catching the train/serve skew
    with pytest.raises(ValueError, match="Feature dimension mismatch"):
        clf.predict_probability([0.0] * 12)

    # Full 24-feature vector should succeed
    prob = clf.predict_probability([0.0] * 24)
    assert 0.0 <= prob <= 1.0


def test_w2_config_unification() -> None:
    """W2: Ensure config/fall_detection_v3.yaml and FallStateMachineConfigV3 match."""
    yaml_path = ROOT / "config" / "fall_detection_v3.yaml"
    assert yaml_path.is_file(), f"Missing {yaml_path}"

    cfg_from_yaml = FallStateMachineConfigV3.from_yaml(yaml_path)
    cfg_default = FallStateMachineConfigV3()

    assert cfg_from_yaml.feature_window_sec == cfg_default.feature_window_sec == 1.0
    assert (
        cfg_from_yaml.descent_velocity_threshold == cfg_default.descent_velocity_threshold == 0.35
    )
    assert (
        cfg_from_yaml.peak_descent_velocity_threshold
        == cfg_default.peak_descent_velocity_threshold
        == 0.70
    )
    assert cfg_from_yaml.descent_aspect_ratio_drop == cfg_default.descent_aspect_ratio_drop == -0.25
    assert cfg_from_yaml.fallen_aspect_ratio_max == cfg_default.fallen_aspect_ratio_max == 1.10
    assert (
        cfg_from_yaml.fallen_torso_angle_max_deg == cfg_default.fallen_torso_angle_max_deg == 40.0
    )
    assert (
        cfg_from_yaml.classifier_trigger_threshold
        == cfg_default.classifier_trigger_threshold
        == 0.40
    )
    assert (
        cfg_from_yaml.classifier_confirmation_threshold
        == cfg_default.classifier_confirmation_threshold
        == 0.45
    )
    assert cfg_from_yaml.classifier_veto_threshold == cfg_default.classifier_veto_threshold == 0.35


def test_w3_two_stage_confirmation_and_veto() -> None:
    """W3: Ensure classifier actively vetoes false alerts when prob < veto threshold."""
    # 1. State machine with vetoing classifier (prob = 0.10 < veto 0.35)
    veto_clf = DummyMockClassifier(fixed_prob=0.10)
    sm_veto = TrackFallStateMachineV3(
        camera_id="cam1",
        track_id=1,
        classifier=veto_clf,
    )

    history: list[TrackObservation] = []
    for i in range(5):
        history.append(_make_observation(timestamp=i * 0.1, y_center=50, bbox_h=100, bbox_w=30))
    sm_veto.update(history)

    # Rapid descent
    history.append(_make_observation(timestamp=0.5, y_center=150, bbox_h=100, bbox_w=30))
    state, _ = sm_veto.update(history)
    assert state == FallState.DESCENT_CANDIDATE

    # Down confirming frames
    for t in [0.6, 0.7, 0.8, 0.9]:
        history.append(
            _make_observation(timestamp=t, y_center=150, bbox_h=30, bbox_w=100, is_down=True)
        )
        sm_veto.update(history)

    # Sustained low posture beyond down_confirmation_sec (0.6s)
    for i in range(10, 18):
        history.append(
            _make_observation(timestamp=i * 0.1, y_center=150, bbox_h=30, bbox_w=100, is_down=True)
        )
        state, event = sm_veto.update(history)
        if state == FallState.NORMAL:
            break

    # Must be vetoed back to NORMAL; zero event emitted!
    assert state == FallState.NORMAL
    assert sm_veto.confirmed_event is None

    # 2. State machine with confirming classifier (prob = 0.95 >= 0.45)
    confirm_clf = DummyMockClassifier(fixed_prob=0.95)
    sm_confirm = TrackFallStateMachineV3(
        camera_id="cam1",
        track_id=2,
        classifier=confirm_clf,
    )

    history_confirm: list[TrackObservation] = []
    for i in range(5):
        history_confirm.append(
            _make_observation(timestamp=i * 0.1, y_center=50, bbox_h=100, bbox_w=30, track_id=2)
        )
    sm_confirm.update(history_confirm)

    history_confirm.append(
        _make_observation(timestamp=0.5, y_center=150, bbox_h=100, bbox_w=30, track_id=2)
    )
    sm_confirm.update(history_confirm)

    for i in range(6, 18):
        history_confirm.append(
            _make_observation(
                timestamp=i * 0.1, y_center=150, bbox_h=30, bbox_w=100, is_down=True, track_id=2
            )
        )
        state, event = sm_confirm.update(history_confirm)
        if state == FallState.FALL_CONFIRMED:
            break

    assert state == FallState.FALL_CONFIRMED
    assert event is not None


def test_w4_default_classifier_v3() -> None:
    """W4: Ensure TrackFallStateMachineV3 and FallStateMachineManagerV3 default to V3 classifier."""
    sm = TrackFallStateMachineV3(camera_id="cam1", track_id=1)
    # Must not be V2 LearnedTemporalFallClassifier
    assert sm.classifier.__class__.__name__ != "LearnedTemporalFallClassifier"
    assert isinstance(sm.classifier, (LogisticClassifierV3, TemporalClassifierV3Base))

    mgr = FallStateMachineManagerV3()
    assert mgr.classifier.__class__.__name__ != "LearnedTemporalFallClassifier"
    assert isinstance(mgr.classifier, (LogisticClassifierV3, TemporalClassifierV3Base))

    default_clf = _get_default_v3_classifier()
    assert default_clf is not None
    assert default_clf.feature_dim == 24


def test_w5_track_stitching_wired() -> None:
    """W5: Ensure TrackStitcher is wired in manager and bytetrack_v3.yaml is present."""
    bytetrack_cfg = ROOT / "config" / "bytetrack_v3.yaml"
    assert bytetrack_cfg.is_file(), f"Missing {bytetrack_cfg}"
    content = bytetrack_cfg.read_text(encoding="utf-8")
    assert "track_buffer: 60" in content

    mgr = FallStateMachineManagerV3()
    assert mgr.stitcher is not None

    # Track 1 appears
    obs_t1 = [
        _make_observation(timestamp=i / 30.0, track_id=1, y_center=50, bbox_h=100, bbox_w=30)
        for i in range(10)
    ]
    mgr.stitcher.register_lost_track(1, obs_t1)

    # Track 2 appears nearby shortly after
    obs_t2 = [
        _make_observation(timestamp=0.35, track_id=2, y_center=52, bbox_h=100, bbox_w=30),
        _make_observation(timestamp=0.38, track_id=2, y_center=54, bbox_h=100, bbox_w=30),
    ]
    canonical_id = mgr.resolve_canonical_track_id(2, obs_t2)
    assert canonical_id == 1  # Successfully stitched to track 1!


def test_w6_features_schema_improvements() -> None:
    """W6: Ensure scale_normalized_stability and low_confidence_keypoint_count are exposed."""
    obs_list = [
        _make_observation(timestamp=i * 0.1, y_center=50 + i * 2, bbox_h=100, bbox_w=30)
        for i in range(5)
    ]
    feats = extract_temporal_features_v3(obs_list)
    assert hasattr(feats, "scale_normalized_stability")
    assert hasattr(feats, "low_confidence_keypoint_count")
    assert feats.scale_normalized_stability >= 0.0
    assert len(feats.feature_vector) == 24
