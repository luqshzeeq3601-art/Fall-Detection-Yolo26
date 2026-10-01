"""Track-history sequence integration test (P3-003).

Multi-frame ``TrackedFrame`` sequence (scripted backend via ``PoseTracker``)
→ per-frame ``tracked_frame_to_observations`` → ``TrackHistory.append`` over
4 frames x 2 persons → per-track snapshots show identity-continuous,
order-correct, bounded histories. The consumer blocks below group/read
histories using ONLY store + ``TrackObservation`` APIs (no tracker or
framework knowledge). CPU-only: hand-built frames, zero sleeps, no
ultralytics/torch/cv2.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import (
    TrackObservation,
    tracked_frame_to_observations,
)
from eldercare.vision.tracking.tracker import PoseTracker

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


def _keypoints() -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(x=float(i * 2), y=float(i * 2 + 1), confidence=0.5, present=True)
        for i in range(17)
    )


def _person(bbox: tuple[float, float, float, float], det_conf: float = 0.8) -> PersonPose:
    return PersonPose(bbox_xyxy=bbox, detection_confidence=det_conf, keypoints=_keypoints())


def _image() -> np.ndarray:
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def _run_frames(
    tracker: PoseTracker,
    history: TrackHistory,
    frames: list[PoseFrame],
) -> list[tuple[TrackObservation, ...]]:
    """Drive the pipeline path: tracker → converter → history store."""
    batches: list[tuple[TrackObservation, ...]] = []
    for step, frame in enumerate(frames):
        tracked = tracker.update(frame, _image())
        batch = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=float(step))
        for obs in batch:
            history.append(obs)
        batches.append(batch)
    return batches


def test_four_frame_two_person_identity_continuous_bounded() -> None:
    left_boxes = [
        (10.0, 20.0, 60.0, 120.0),
        (12.0, 20.0, 62.0, 120.0),
        (14.0, 20.0, 64.0, 120.0),
        (16.0, 20.0, 66.0, 120.0),
    ]
    right_boxes = [
        (200.0, 100.0, 300.0, 250.0),
        (202.0, 100.0, 302.0, 250.0),
        (204.0, 101.0, 304.0, 251.0),
        (206.0, 101.0, 306.0, 251.0),
    ]
    backend = ScriptedBackend([(1, 2), (1, 2), (1, None), (1, 2)])
    tracker = PoseTracker(backend=backend)
    history = TrackHistory()
    frames = [
        PoseFrame(WIDTH, HEIGHT, (_person(left), _person(right)))
        for left, right in zip(left_boxes, right_boxes, strict=True)
    ]
    batches = _run_frames(tracker, history, frames)
    assert all(len(batch) == 2 for batch in batches)

    # Consumer block: ONLY store + TrackObservation APIs from here on.
    left_track = history.snapshot(CAMERA_ID, 1)
    right_track = history.snapshot(CAMERA_ID, 2)
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 2))
    assert [obs.timestamp for obs in left_track] == [0.0, 1.0, 2.0, 3.0]
    assert [obs.timestamp for obs in right_track] == [0.0, 1.0, 3.0]
    assert all(obs.track_id == 1 for obs in left_track)
    assert all(obs.track_id == 2 for obs in right_track)
    assert all(obs.camera_id == CAMERA_ID for obs in left_track + right_track)
    assert [obs.bbox_xyxy for obs in left_track] == left_boxes
    assert [obs.bbox_xyxy for obs in right_track] == [
        right_boxes[0],
        right_boxes[1],
        right_boxes[3],
    ]


def test_long_sequence_evicts_oldest_newest_retained() -> None:
    backend = ScriptedBackend([(5,)] * 6)
    tracker = PoseTracker(backend=backend)
    history = TrackHistory(TrackHistoryConfig(max_observations=3))
    boxes = [(10.0 + step, 20.0, 60.0 + step, 120.0) for step in range(6)]
    frames = [PoseFrame(WIDTH, HEIGHT, (_person(box),)) for box in boxes]
    _run_frames(tracker, history, frames)

    # Consumer block: ONLY store + TrackObservation APIs from here on.
    assert len(history) == 1
    track = history.snapshot(CAMERA_ID, 5)
    assert len(track) == 3
    assert [obs.timestamp for obs in track] == [3.0, 4.0, 5.0]
    assert [obs.bbox_xyxy for obs in track] == boxes[3:]
