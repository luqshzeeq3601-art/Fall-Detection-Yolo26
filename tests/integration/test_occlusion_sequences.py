"""Occlusion-sequence integration tests (P3-005, TEST-ONLY).

Multi-frame ``PoseFrame`` sequences (>= 4 frames: 2-person cross + 1-person
gap + reorder) through the full chain — scripted fake ByteTrack IDs via
``PoseTracker`` -> ``tracked_frame_to_observations`` -> ``TrackHistory``
(+ one ``expire_stale`` pass) — proving identity isolation end to end,
consumable without tracker knowledge. CPU-only, synthetic inline fixtures,
zero sleeps, no ultralytics/torch/cv2.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import numpy as np

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import tracked_frame_to_observations
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


def _keypoints(base: float, conf: float = 0.5) -> tuple[Keypoint, ...]:
    coords = np.arange(34, dtype=np.float64).reshape(17, 2) + base
    return tuple(
        Keypoint(x=float(coords[i, 0]), y=float(coords[i, 1]), confidence=conf, present=True)
        for i in range(17)
    )


def _person(bbox: tuple[float, float, float, float], det_conf: float, base: float) -> PersonPose:
    return PersonPose(bbox_xyxy=bbox, detection_confidence=det_conf, keypoints=_keypoints(base))


def _image() -> np.ndarray:
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def _run_chain(
    frames: tuple[PoseFrame, ...], scripts: list[tuple[int | None, ...]]
) -> tuple[TrackHistory, list[tuple[Any, ...]]]:
    tracker = PoseTracker(backend=ScriptedBackend(scripts))
    history = TrackHistory(TrackHistoryConfig())
    batches = []
    for step, frame in enumerate(frames):
        batch = tracked_frame_to_observations(
            tracker.update(frame, _image()), camera_id=CAMERA_ID, timestamp=float(step)
        )
        for obs in batch:
            history.append(obs)
        batches.append(batch)
    return history, batches


def _frame(persons: tuple[PersonPose, ...] = ()) -> PoseFrame:
    return PoseFrame(image_width=WIDTH, image_height=HEIGHT, persons=persons)


def test_cross_gap_reorder_chain_end_to_end() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.6, 100.0)
    cross_a = _person((105.0, 60.0, 155.0, 160.0), 0.8, 0.0)
    cross_b = _person((95.0, 55.0, 145.0, 155.0), 0.6, 100.0)
    lone_a = _person((120.0, 65.0, 170.0, 165.0), 0.8, 0.0)
    back_b = _person((60.0, 40.0, 110.0, 140.0), 0.6, 100.0)
    back_a = _person((130.0, 70.0, 180.0, 170.0), 0.8, 0.0)
    final_a = _person((140.0, 75.0, 190.0, 175.0), 0.8, 0.0)
    final_b = _person((50.0, 35.0, 100.0, 135.0), 0.6, 100.0)
    frames = (
        _frame((person_a, person_b)),
        _frame((cross_a, cross_b)),
        _frame((lone_a,)),
        _frame((back_b, back_a)),
        _frame((final_a, final_b)),
    )
    scripts = [(1, 2), (1, 2), (1,), (2, 1), (1, 2)]
    history, batches = _run_chain(frames, scripts)
    assert [len(batch) for batch in batches] == [2, 2, 1, 2, 2]
    expired = history.expire_stale(4.0, max_idle_seconds=10.0)
    assert expired == ()
    snap_1 = history.snapshot(CAMERA_ID, 1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert [obs.bbox_xyxy for obs in snap_1] == [
        person_a.bbox_xyxy,
        cross_a.bbox_xyxy,
        lone_a.bbox_xyxy,
        back_a.bbox_xyxy,
        final_a.bbox_xyxy,
    ]
    assert [obs.bbox_xyxy for obs in snap_2] == [
        person_b.bbox_xyxy,
        cross_b.bbox_xyxy,
        back_b.bbox_xyxy,
        final_b.bbox_xyxy,
    ]
    assert [obs.timestamp for obs in snap_1] == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert [obs.timestamp for obs in snap_2] == [0.0, 1.0, 3.0, 4.0]
    assert all(obs.track_id == 1 for obs in snap_1)
    assert all(obs.track_id == 2 for obs in snap_2)
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 2))


def test_gap_fork_chain_end_to_end() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.8, 0.0)
    person_new = _person((300.0, 60.0, 350.0, 160.0), 0.5, 500.0)
    person_new2 = _person((304.0, 62.0, 354.0, 162.0), 0.5, 500.0)
    frames = (
        _frame((person_a,)),
        _frame((person_a2,)),
        _frame(()),
        _frame((person_new,)),
        _frame((person_new2,)),
    )
    scripts = [(1,), (1,), (), (9,), (9,)]
    history, batches = _run_chain(frames, scripts)
    assert [len(batch) for batch in batches] == [1, 1, 0, 1, 1]
    assert history.expire_stale(4.0, max_idle_seconds=10.0) == ()
    snap_old = history.snapshot(CAMERA_ID, 1)
    snap_new = history.snapshot(CAMERA_ID, 9)
    assert [obs.timestamp for obs in snap_old] == [0.0, 1.0]
    assert [obs.timestamp for obs in snap_new] == [3.0, 4.0]
    assert [obs.bbox_xyxy for obs in snap_old] == [person_a.bbox_xyxy, person_a2.bbox_xyxy]
    assert [obs.bbox_xyxy for obs in snap_new] == [person_new.bbox_xyxy, person_new2.bbox_xyxy]


def test_cross_camera_same_ids_chain_end_to_end() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.6, 100.0)
    history = TrackHistory(TrackHistoryConfig())
    for camera_id, person in (("cam-a", person_a), ("cam-b", person_b)):
        tracker = PoseTracker(backend=ScriptedBackend([(3,), (3,)]))
        for step in range(2):
            batch = tracked_frame_to_observations(
                tracker.update(_frame((person,)), _image()),
                camera_id=camera_id,
                timestamp=float(step),
            )
            for obs in batch:
                history.append(obs)
    assert history.expire_stale(1.0, max_idle_seconds=10.0) == ()
    snap_a = history.snapshot("cam-a", 3)
    snap_b = history.snapshot("cam-b", 3)
    assert [obs.bbox_xyxy for obs in snap_a] == [person_a.bbox_xyxy] * 2
    assert [obs.bbox_xyxy for obs in snap_b] == [person_b.bbox_xyxy] * 2
    assert history.keys() == (("cam-a", 3), ("cam-b", 3))


def test_none_mix_and_zero_person_chain_end_to_end() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.6, 100.0)
    frames = (
        _frame((person_a, person_b)),
        _frame((person_a, person_b)),
        _frame(()),
        _frame((person_b, person_a)),
    )
    scripts = [(1, None), (None, 1), (), (2, 1)]
    history, batches = _run_chain(frames, scripts)
    assert [len(batch) for batch in batches] == [2, 2, 0, 2]
    assert history.expire_stale(3.0, max_idle_seconds=10.0) == ()
    snap_1 = history.snapshot(CAMERA_ID, 1)
    # IDs follow content across the None mixes: A(t0) -> B(t1) -> A(t3).
    assert [obs.bbox_xyxy for obs in snap_1] == [
        person_a.bbox_xyxy,
        person_b.bbox_xyxy,
        person_a.bbox_xyxy,
    ]
    assert [obs.timestamp for obs in snap_1] == [0.0, 1.0, 3.0]
    assert all(obs.track_id == 1 for obs in snap_1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert len(snap_2) == 1
    assert snap_2[0].bbox_xyxy == person_b.bbox_xyxy
    assert set(history.keys()) == {(CAMERA_ID, 1), (CAMERA_ID, 2)}


def test_full_sequence_determinism_end_to_end() -> None:
    def run_once() -> TrackHistory:
        person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
        person_b = _person((200.0, 100.0, 300.0, 250.0), 0.6, 100.0)
        frames = (
            _frame((person_a, person_b)),
            _frame((person_b, person_a)),
            _frame((person_a,)),
            _frame((person_b, person_a)),
        )
        scripts = [(1, 2), (2, 1), (1,), (2, 1)]
        history, _ = _run_chain(frames, scripts)
        history.expire_stale(3.0, max_idle_seconds=10.0)
        return history

    first_run = run_once()
    second_run = run_once()
    assert first_run.keys() == second_run.keys()
    for key in first_run.keys():
        assert first_run.snapshot(*key) == second_run.snapshot(*key)


def test_runtime_and_ast_freedom() -> None:
    before = set(sys.modules)
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.8, 0.0)
    history, _ = _run_chain((_frame((person_a,)),), [(1,)])
    history.expire_stale(0.0, max_idle_seconds=10.0)
    introduced = set(sys.modules) - before
    assert not introduced & set(_FORBIDDEN_RUNTIME_MODULES)
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
    assert not [root for root in roots if root in _FORBIDDEN_RUNTIME_MODULES]
