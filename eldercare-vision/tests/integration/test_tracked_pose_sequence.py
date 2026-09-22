"""Tracked pose sequence integration test (P3-001).

PoseFrame sequence (>= 3 frames, scripted backend) -> TrackedFrame observations
with ``track_id`` stable per person across frames and independent across
persons. CPU-only: hand-built frames, zero sleeps, no ultralytics/torch/cv2.
"""

from __future__ import annotations

import sys
from typing import Any

import numpy as np

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.tracker import PoseTracker

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

HEIGHT = 480
WIDTH = 640


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


def _walking_bboxes() -> list[tuple[float, float, float, float]]:
    """One person drifting right across three frames (slight bbox motion)."""
    return [
        (10.0, 20.0, 60.0, 120.0),
        (14.0, 20.0, 64.0, 120.0),
        (18.0, 21.0, 68.0, 121.0),
    ]


def _image() -> np.ndarray:
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def test_three_frame_single_person_id_stable() -> None:
    backend = ScriptedBackend([(42,), (42,), (42,)])
    tracker = PoseTracker(backend=backend)
    frames = [_walking_bboxes()[i] for i in range(3)]
    tracked = [
        tracker.update(PoseFrame(WIDTH, HEIGHT, (_person(bbox),)), _image()) for bbox in frames
    ]
    assert [t.persons[0].track_id for t in tracked] == [42, 42, 42]
    assert backend.calls == 3
    for frame_tracked, bbox in zip(tracked, frames, strict=True):
        assert frame_tracked.persons[0].person.bbox_xyxy == bbox
        assert (frame_tracked.image_width, frame_tracked.image_height) == (WIDTH, HEIGHT)


def test_multi_person_independence_end_to_end() -> None:
    left_boxes = [(10.0, 20.0, 60.0, 120.0), (12.0, 20.0, 62.0, 120.0), (14.0, 20.0, 64.0, 120.0)]
    right_boxes = [
        (200.0, 100.0, 300.0, 250.0),
        (202.0, 100.0, 302.0, 250.0),
        (204.0, 101.0, 304.0, 251.0),
    ]
    backend = ScriptedBackend([(1, 2), (1, 2), (1, 2)])
    tracker = PoseTracker(backend=backend)
    tracked = [
        tracker.update(PoseFrame(WIDTH, HEIGHT, (_person(left), _person(right))), _image())
        for left, right in zip(left_boxes, right_boxes, strict=True)
    ]
    for frame_tracked in tracked:
        assert [p.track_id for p in frame_tracked.persons] == [1, 2]
    assert (
        tracked[0].persons[0].person is not tracked[1].persons[0].person
    )  # no cross-frame aliasing
    assert tracked[2].persons[1].person.bbox_xyxy == right_boxes[2]


def test_disappearance_mid_sequence_end_to_end() -> None:
    bbox = (10.0, 20.0, 60.0, 120.0)
    backend = ScriptedBackend([(5,), (), (5,)])
    tracker = PoseTracker(backend=backend)
    present = PoseFrame(WIDTH, HEIGHT, (_person(bbox),))
    absent = PoseFrame(WIDTH, HEIGHT, ())
    first = tracker.update(present, _image())
    middle = tracker.update(absent, _image())
    last = tracker.update(present, _image())
    assert first.persons[0].track_id == 5
    assert middle.persons == ()
    assert last.persons[0].track_id == 5  # backend re-issues; our code invents nothing
    assert backend.calls == 3
    before = set(sys.modules)
    assert not (set(sys.modules) - before) & set(_FORBIDDEN_RUNTIME_MODULES)
