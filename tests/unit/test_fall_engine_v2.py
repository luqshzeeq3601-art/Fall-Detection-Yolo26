"""Unit tests for Fall Engine v2 (Phase 11.5).

Tests scale-normalized features, learned classifier, and state machine v2.
"""

from __future__ import annotations

import pytest

from eldercare.fall_engine.features.geometry_v2 import extract_geometry_features_v2
from eldercare.fall_engine.features.motion_v2 import extract_temporal_features_v2
from eldercare.fall_engine.learned_classifier.classifier import (
    LearnedTemporalFallClassifier,
)
from eldercare.fall_engine.state_machine.states import FallState
from eldercare.fall_engine.state_machine_v2.config_v2 import FallStateMachineConfigV2
from eldercare.fall_engine.state_machine_v2.machine_v2 import (
    FallStateMachineManagerV2,
    TrackFallStateMachineV2,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def _make_observation(
    timestamp: float,
    bbox: tuple[float, float, float, float],
    keypoints: list[Keypoint] | None = None,
    track_id: int = 1,
) -> TrackObservation:
    """Helper to create TrackObservation with 17 keypoints."""
    if keypoints is None:
        keypoints = [
            Keypoint(
                x=bbox[0] + (bbox[2] - bbox[0]) / 2.0,
                y=bbox[1] + (bbox[3] - bbox[1]) * (i / 17.0),
                confidence=0.9,
                present=True,
            )
            for i in range(17)
        ]
    return TrackObservation(
        camera_id="cam_test",
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=bbox,
        detection_confidence=0.95,
        keypoints=tuple(keypoints),
        image_width=640,
        image_height=480,
    )


class TestGeometryAndMotionV2:
    def test_geometry_v2_extraction(self) -> None:
        obs = _make_observation(0.0, (100.0, 100.0, 200.0, 300.0))
        geom = extract_geometry_features_v2(obs)
        assert geom.bbox_width == 100.0
        assert geom.bbox_height == 200.0
        assert geom.aspect_ratio == 2.0
        assert geom.keypoints_present_count == 17
        assert geom.keypoint_confidence_mean > 0.8

    def test_motion_v2_scale_normalization(self) -> None:
        # 1. Standing observation (height = 200)
        obs1 = _make_observation(0.0, (100.0, 100.0, 200.0, 300.0))
        # 2. Descending observation (height = 150, lower Y)
        obs2 = _make_observation(0.2, (100.0, 150.0, 220.0, 300.0))
        # 3. Fallen observation (horizontal, height = 60, width = 180, on floor)
        obs3 = _make_observation(0.5, (100.0, 240.0, 280.0, 300.0))

        feats = extract_temporal_features_v2([obs1, obs2, obs3], window_seconds=1.0)
        assert feats.reference_height >= 180.0
        assert feats.vertical_displacement > 0.0
        assert feats.scale_normalized_vertical_velocity > 0.0
        assert len(feats.feature_vector) == 12


class TestLearnedClassifier:
    def test_classifier_prediction_and_contributions(self, tmp_path) -> None:
        classifier = LearnedTemporalFallClassifier()

        # Obvious fall feature vector: high downward velocity, low aspect ratio, low torso angle
        fall_feats = (1.5, 2.0, 0.8, 0.5, -0.6, 15.0, -60.0, -0.6, 1.0, 5.0, 0.9, 0.8)
        prob_fall = classifier.predict_probability(fall_feats)
        assert prob_fall > 0.80
        assert classifier.is_fall(fall_feats) is True

        # Obvious normal standing: zero velocity, tall aspect ratio, vertical angle
        normal_feats = (0.0, 0.0, 0.0, 2.2, 0.0, 85.0, 0.0, 0.0, 0.0, 0.0, 0.9, 0.4)
        prob_normal = classifier.predict_probability(normal_feats)
        assert prob_normal < 0.20
        assert classifier.is_fall(normal_feats) is False

        # Explainable breakdown
        breakdown = classifier.get_feature_contributions(fall_feats)
        assert "probability" in breakdown
        assert "contributions" in breakdown
        assert breakdown["is_fall"] is True

        # Save and reload
        save_file = tmp_path / "classifier_weights.json"
        classifier.save_to_json(save_file)
        loaded = LearnedTemporalFallClassifier.load_from_json(save_file)
        assert loaded.predict_probability(fall_feats) == pytest.approx(prob_fall, abs=1e-5)


class TestStateMachineV2:
    def test_state_machine_v2_fall_progression(self) -> None:
        config = FallStateMachineConfigV2(
            descent_velocity_threshold=0.3,
            down_confirmation_sec=0.4,
            use_learned_classifier=True,
        )
        sm = TrackFallStateMachineV2(camera_id="cam0", track_id=1, config=config)

        history = []
        # Frame 0: Standing
        obs0 = _make_observation(0.0, (100.0, 100.0, 200.0, 300.0))
        history.append(obs0)
        state, event = sm.update(history)
        assert state == FallState.NORMAL
        assert event is None

        # Frame 1: Rapid descent
        obs1 = _make_observation(0.2, (100.0, 180.0, 220.0, 320.0))
        history.append(obs1)
        state, event = sm.update(history)
        assert state in (FallState.DESCENT_CANDIDATE, FallState.DOWN_CONFIRMING)

        # Frame 2: Down posture
        obs2 = _make_observation(0.4, (100.0, 240.0, 280.0, 310.0))
        history.append(obs2)
        state, event = sm.update(history)
        assert state == FallState.DOWN_CONFIRMING

        # Frame 3: Sustained down posture confirming fall
        obs3 = _make_observation(0.9, (100.0, 240.0, 280.0, 310.0))
        history.append(obs3)
        state, event = sm.update(history)
        assert state == FallState.FALL_CONFIRMED
        assert event is not None
        assert event.confidence > 0.5

    def test_manager_v2_lifecycle(self) -> None:
        mgr = FallStateMachineManagerV2()
        obs = _make_observation(0.0, (100.0, 100.0, 200.0, 300.0), track_id=5)
        state, event = mgr.update_track("cam1", 5, [obs])
        assert state == FallState.NORMAL
        assert mgr.active_tracks_count == 1
        removed = mgr.cleanup_expired_tracks(set())
        assert removed == 1
        assert mgr.active_tracks_count == 0
