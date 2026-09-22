"""Track-observation sequence integration test (P3-002).

2-3 frame ``TrackedFrame`` sequence (scripted backend via ``PoseTracker``) →
per-frame ``tracked_frame_to_observations`` → per-track identity continuity
observable WITHOUT tracker knowledge (the consumer reads only
``TrackObservation`` fields). CPU-only: hand-built frames, zero sleeps, no
ultralytics/torch/cv2.
"""

from __future__ import annotations

import sys
from typing import Any

import numpy as np

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.observation import (
    TrackObservation,
    tracked_frame_to_observations,
)
from eldercare.vision.tracking.tracker import PoseTracker

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

HEIGHT = 480
WIDTH = 640
CAMERA_ID = "cam-01"


class ScriptedBackend:
    """TrackBackend fake: replays one scripted id-tuple per ``track`` call."""

    def __init__(self, scripts: list[tuple[int | None, ...]]) -> None:
        self._scripts = [tuple(script) for script in scripts]
        self.calls = 0

    def track(
        self, detections: tuple[tuple[float, float, float, float], ...], image: Any
    ) -> tuple[int | None, ...]:
        self.calls += 1
        if self.calls <= len(self._scripts):
            return self._scripts[self.calls - 1]
        return self._scripts[-1]


def _keypoints(offset: float = 0.0) -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(
            x=offset + float(i * 2),
            y=offset + float(i * 2 + 1),
            confidence=0.5,
            present=True,
        )
        for i in range(17)
    )


def _person(bbox: tuple[float, float, float, float], det_conf: float = 0.8) -> PersonPose:
    return PersonPose(bbox_xyxy=bbox, detection_confidence=det_conf, keypoints=_keypoints())


def _image() -> np.ndarray:
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def _group(
    observations: list[tuple[TrackObservation, ...]],
) -> dict[tuple[str, int | None], list[TrackObservation]]:
    """Test-local consumer grouping: keyed ONLY by TrackObservation fields."""
    groups: dict[tuple[str, int | None], list[TrackObservation]] = {}
    for batch in observations:
        for obs in batch:
            groups.setdefault((obs.camera_id, obs.track_id), []).append(obs)
    return groups


def test_two_frame_sequence_identity_continuity_via_observations() -> None:
    backend = ScriptedBackend([(7,), (7,)])
    tracker = PoseTracker(backend=backend)
    bboxes = [(10.0, 20.0, 60.0, 120.0), (14.0, 20.0, 64.0, 120.0)]
    batches = [
        tracked_frame_to_observations(
            tracker.update(PoseFrame(WIDTH, HEIGHT, (_person(bbox),)), _image()),
            camera_id=CAMERA_ID,
            timestamp=float(step),
        )
        for step, bbox in enumerate(bboxes)
    ]
    assert all(len(batch) == 1 for batch in batches)
    assert [batch[0].track_id for batch in batches] == [7, 7]
    assert [batch[0].timestamp for batch in batches] == [0.0, 1.0]
    assert batches[0][0].bbox_xyxy == bboxes[0]
    assert batches[1][0].bbox_xyxy == bboxes[1]
    groups = _group(batches)
    assert list(groups) == [(CAMERA_ID, 7)]
    assert len(groups[(CAMERA_ID, 7)]) == 2


def test_disappearance_and_reappearance_grouping() -> None:
    bbox = (10.0, 20.0, 60.0, 120.0)
    backend = ScriptedBackend([(5,), (), (5,)])
    tracker = PoseTracker(backend=backend)
    present = PoseFrame(WIDTH, HEIGHT, (_person(bbox),))
    absent = PoseFrame(WIDTH, HEIGHT, ())
    batches = [
        tracked_frame_to_observations(
            tracker.update(frame, _image()), camera_id=CAMERA_ID, timestamp=float(step)
        )
        for step, frame in enumerate((present, absent, present))
    ]
    assert [batch[0].track_id if batch else None for batch in batches] == [5, None, 5]
    assert batches[1] == ()
    groups = _group(batches)
    assert [obs.timestamp for obs in groups[(CAMERA_ID, 5)]] == [0.0, 2.0]
    before = set(sys.modules)
    assert not (set(sys.modules) - before) & set(_FORBIDDEN_RUNTIME_MODULES)


def test_multi_person_tracks_stay_independent_without_tracker_knowledge() -> None:
    left_boxes = [(10.0, 20.0, 60.0, 120.0), (12.0, 20.0, 62.0, 120.0), (14.0, 20.0, 64.0, 120.0)]
    right_boxes = [
        (200.0, 100.0, 300.0, 250.0),
        (202.0, 100.0, 302.0, 250.0),
        (204.0, 101.0, 304.0, 251.0),
    ]
    backend = ScriptedBackend([(1, 2), (1, 2), (1, None)])
    tracker = PoseTracker(backend=backend)
    batches = [
        tracked_frame_to_observations(
            tracker.update(PoseFrame(WIDTH, HEIGHT, (_person(left), _person(right))), _image()),
            camera_id=CAMERA_ID,
            timestamp=float(step),
        )
        for step, (left, right) in enumerate(zip(left_boxes, right_boxes, strict=True))
    ]
    groups = _group(batches)
    assert set(groups) == {(CAMERA_ID, 1), (CAMERA_ID, 2), (CAMERA_ID, None)}
    assert len(groups[(CAMERA_ID, 1)]) == 3
    assert len(groups[(CAMERA_ID, 2)]) == 2
    assert groups[(CAMERA_ID, None)][0].bbox_xyxy == right_boxes[2]
    assert groups[(CAMERA_ID, None)][0].timestamp == 2.0
