import pytest
import math
from typing import List
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.state_machine_v3.machine_v3 import TrackFallStateMachineV3
from eldercare.fall_engine.evaluation.runner_v3 import SequenceEvaluationRunnerV3
from eldercare.fall_engine.evaluation.manifest import SequenceManifestRecord
from eldercare.fall_engine.state_machine.states import FallState

def create_observation(
    timestamp: float,
    y_center: float = 50.0,
    bbox_h: float = 100.0,
    bbox_w: float = 30.0,
    is_down: bool = False,
    track_id: int = 1
) -> TrackObservation:
    x_center = 50.0
    x1, y1 = x_center - bbox_w/2, y_center - bbox_h/2
    x2, y2 = x_center + bbox_w/2, y_center + bbox_h/2
    
    # Generate 17 mock keypoints
    kpts = []
    for i in range(17):
        k = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9)
        kpts.append(k)
        
    # Adjust torso angle implicitly by modifying shoulders and hips
    if is_down:
        # lay flat
        kpts[5] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9) # L shoulder
        kpts[6] = Keypoint(present=True, x=x1, y=y_center, confidence=0.9) # R shoulder
        kpts[11] = Keypoint(present=True, x=x2, y=y_center, confidence=0.9) # L hip
        kpts[12] = Keypoint(present=True, x=x2, y=y_center, confidence=0.9) # R hip
    else:
        # upright
        kpts[5] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9) # L shoulder
        kpts[6] = Keypoint(present=True, x=x_center, y=y1, confidence=0.9) # R shoulder
        kpts[11] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9) # L hip
        kpts[12] = Keypoint(present=True, x=x_center, y=y_center, confidence=0.9) # R hip
        
    return TrackObservation(
        camera_id="cam1",
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=(x1, y1, x2, y2),
        keypoints=kpts,
        image_width=100,
        image_height=100,
        detection_confidence=0.9
    )

def test_v3_basic_transitions():
    sm = TrackFallStateMachineV3(camera_id="cam1", track_id=1)
    history = []
    
    # 1. NORMAL
    for i in range(5):
        history.append(create_observation(timestamp=i*0.1, y_center=50, bbox_h=100, bbox_w=30))
    state, event = sm.update(history)
    assert state == FallState.NORMAL
    
    # 2. DESCENT_CANDIDATE (rapid drop)
    history.append(create_observation(timestamp=0.5, y_center=150, bbox_h=100, bbox_w=30))
    state, event = sm.update(history)
    assert state == FallState.DESCENT_CANDIDATE
    
    # 3. DOWN_CONFIRMING (low posture sustained)
    history.append(create_observation(timestamp=0.6, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
    state, event = sm.update(history)
    
    history.append(create_observation(timestamp=0.7, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
    state, event = sm.update(history)
    
    history.append(create_observation(timestamp=0.8, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
    state, event = sm.update(history)
    
    history.append(create_observation(timestamp=0.9, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
    state, event = sm.update(history)
    
    assert state == FallState.DOWN_CONFIRMING
    
    # 4. FALL_CONFIRMED
    for i in range(10, 20):
        history.append(create_observation(timestamp=i*0.1, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
        state, event = sm.update(history)
        if state == FallState.FALL_CONFIRMED:
            break
    assert state == FallState.FALL_CONFIRMED
    assert event is not None
    
    # 5. RECOVERY
    history.append(create_observation(timestamp=2.5, y_center=50, bbox_h=100, bbox_w=30))
    state, event = sm.update(history)
    assert state == FallState.RECOVERY

def test_v3_timeout():
    sm = TrackFallStateMachineV3(camera_id="cam1", track_id=1)
    history = []
    
    # NORMAL
    for i in range(5):
        history.append(create_observation(timestamp=i*0.1, y_center=50, bbox_h=100, bbox_w=30))
    
    # Trigger descent
    history.append(create_observation(timestamp=0.5, y_center=150, bbox_h=100, bbox_w=30))
    state, _ = sm.update(history)
    assert state == FallState.DESCENT_CANDIDATE
    
    # Timeout by advancing time without low posture
    history.append(create_observation(timestamp=2.0, y_center=150, bbox_h=100, bbox_w=30))
    state, _ = sm.update(history)
    assert state == FallState.NORMAL

def test_v3_evaluation_runner():
    runner = SequenceEvaluationRunnerV3()
    
    obs = []
    for i in range(5):
        obs.append(create_observation(timestamp=i*0.1, y_center=50, bbox_h=100, bbox_w=30))
    # fall
    for i in range(5, 20):
        obs.append(create_observation(timestamp=i*0.1, y_center=150, bbox_h=30, bbox_w=100, is_down=True))
        
    record = SequenceManifestRecord(
        sample_id="test1",
        sequence_id="seq1",
        camera_id="cam1",
        is_fall=True,
        source_dataset="test",
        subject_id="sub1",
        activity="falling",
        fall_type="forward",
        path_local="dummy.mp4",
        split="test",
        license="none",
        notes=""
    )
    
    metrics, results = runner.evaluate_batch([(record, obs, 0.5)])
    assert len(results) == 1
    assert results[0].is_true_positive
    assert metrics.pose_availability_rate > 0

def test_v3_angular_velocity():
    sm = TrackFallStateMachineV3(camera_id="cam1", track_id=1)
    history = []
    for i in range(5):
        history.append(create_observation(timestamp=i*0.1, y_center=50, bbox_h=100, bbox_w=30))
    
    # Rapid torso rotation (implicitly through keypoints changes to is_down=True rapidly without huge y_center drop)
    # Centroid dropping slightly + fast angle change
    history.append(create_observation(timestamp=0.5, y_center=60, bbox_h=80, bbox_w=80, is_down=True))
    state, _ = sm.update(history)
    # Should trigger DESCENT_CANDIDATE via angular velocity or shape change
    assert state == FallState.DESCENT_CANDIDATE
