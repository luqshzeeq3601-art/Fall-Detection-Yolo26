import math
import pytest
from eldercare.fall_engine.features.features_v3 import (
    extract_geometry_features_v3,
    extract_temporal_features_v3,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation

def _make_keypoints(present_list=None, scale=1.0, dy=0.0):
    kpts = []
    for i in range(17):
        if present_list and not present_list[i]:
            kpts.append(Keypoint(x=None, y=None, confidence=0.0, present=False))
        else:
            x = 100 + (i % 2) * 50 * scale
            y = 100 + (i // 5) * 50 * scale + dy
            kpts.append(Keypoint(x=x, y=y, confidence=0.9, present=True))
    return tuple(kpts)

def test_geometry_extraction():
    kpts = _make_keypoints()
    obs = TrackObservation(
        camera_id="cam0",
        track_id=1,
        timestamp=1.0,
        bbox_xyxy=(50.0, 50.0, 250.0, 350.0),
        detection_confidence=0.9,
        keypoints=kpts,
        image_width=640,
        image_height=400
    )
    geom = extract_geometry_features_v3(obs)
    
    assert geom.bbox_width == 200.0
    assert geom.bbox_height == 300.0
    assert geom.keypoints_present_count == 17
    assert len(geom.keypoint_missing_mask) == 17
    assert not any(geom.keypoint_missing_mask)
    assert geom.normalized_head_height is not None
    assert geom.pelvis_center is not None

def test_temporal_extraction():
    history = []
    for i in range(5):
        kpts = _make_keypoints(dy=i * 10.0)
        obs = TrackObservation(
            camera_id="cam0",
            track_id=1,
            timestamp=1.0 + i * 0.1,
            bbox_xyxy=(50.0, 50.0 + i*10, 250.0, 350.0 + i*10),
            detection_confidence=0.9,
            keypoints=kpts,
            image_width=640,
            image_height=400
        )
        history.append(obs)
        
    temp = extract_temporal_features_v3(history)
    assert temp.history_duration_seconds == pytest.approx(0.4)
    assert temp.observation_count == 5
    assert temp.vertical_velocity > 0
    assert temp.cumulative_descent_distance > 0
    assert len(temp.feature_vector) == 24

def test_missing_keypoint_mask():
    p_list = [True] * 17
    p_list[0] = False
    p_list[15] = False
    kpts = _make_keypoints(present_list=p_list)
    obs = TrackObservation(
        camera_id="cam0",
        track_id=1,
        timestamp=1.0,
        bbox_xyxy=(50.0, 50.0, 250.0, 350.0),
        detection_confidence=0.9,
        keypoints=kpts,
        image_width=640,
        image_height=400
    )
    geom = extract_geometry_features_v3(obs)
    assert geom.keypoint_missing_mask[0] == True
    assert geom.keypoint_missing_mask[15] == True
    assert geom.keypoint_missing_mask[1] == False

def test_scale_invariance():
    kpts1 = _make_keypoints(scale=1.0)
    obs1 = TrackObservation("cam0", 1, 1.0, (0.0, 0.0, 200.0, 300.0), 0.9, kpts1, 640, 480)
    g1 = extract_geometry_features_v3(obs1)
    
    kpts2 = _make_keypoints(scale=2.0)
    obs2 = TrackObservation("cam0", 1, 1.0, (0.0, 0.0, 400.0, 600.0), 0.9, kpts2, 640, 480)
    g2 = extract_geometry_features_v3(obs2)
    
    assert g1.shoulder_width_ratio == pytest.approx(g2.shoulder_width_ratio)
    assert g1.hip_width_ratio == pytest.approx(g2.hip_width_ratio)
    assert g1.body_compactness == pytest.approx(g2.body_compactness)

def test_angular_velocity():
    history = []
    for i in range(3):
        kpts = []
        for j in range(17):
            x = 100 + (j % 2) * 50
            y = 100 + (j // 5) * 50
            if j in (5, 6):
                x += i * 20
            kpts.append(Keypoint(x=x, y=y, confidence=0.9, present=True))
            
        obs = TrackObservation(
            camera_id="cam0",
            track_id=1,
            timestamp=1.0 + i * 1.0,
            bbox_xyxy=(0.0, 0.0, 200.0, 300.0),
            detection_confidence=0.9,
            keypoints=tuple(kpts),
            image_width=640,
            image_height=480
        )
        history.append(obs)
        
    temp = extract_temporal_features_v3(history)
    assert temp.angular_velocity_deg_per_sec != 0.0
