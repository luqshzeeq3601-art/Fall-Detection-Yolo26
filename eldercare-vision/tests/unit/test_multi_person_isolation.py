"""Multi-person / occlusion isolation validation (P3-005, TEST-ONLY).

Pins cross-key/cross-frame isolation across the P3-001...P3-004 stack:
project domain state is ALWAYS keyed by ``(camera_id, track_id)`` and NEVER
inferred from person array position, bbox ordering, or pose ordering.

CPU-only: hand-built ``PoseFrame`` objects + scripted ``TrackBackend`` fakes
(programmed ID sequences incl. order swaps, gaps, ``None`` mixes). Synthetic
inline fixtures only (``arange``-style coords + literal tiny values). Neither
this module nor the tracking sources may import ultralytics/torch/cv2 at
runtime — proven by the ``sys.modules`` test and the AST import scans below.

Deliberately NOT re-asserted here (already pinned): single-key append order,
capacity eviction internals, strict-``>`` boundary values, idempotency,
converter field validation, tracker config validation, greedy-IoU helper.
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


# --- builders ---------------------------------------------------------------


def _keypoints(
    base: float, conf: float = 0.5, missing: tuple[int, ...] = ()
) -> tuple[Keypoint, ...]:
    coords = np.arange(34, dtype=np.float64).reshape(17, 2) + base
    points = []
    for index in range(17):
        if index in missing:
            points.append(Keypoint(x=None, y=None, confidence=conf, present=False))
        else:
            points.append(
                Keypoint(
                    x=float(coords[index, 0]),
                    y=float(coords[index, 1]),
                    confidence=conf,
                    present=True,
                )
            )
    return tuple(points)


def _person(
    bbox: tuple[float, float, float, float],
    det_conf: float,
    base: float,
    conf: float = 0.5,
    missing: tuple[int, ...] = (),
) -> PersonPose:
    return PersonPose(
        bbox_xyxy=bbox,
        detection_confidence=det_conf,
        keypoints=_keypoints(base, conf=conf, missing=missing),
    )


def _frame(persons: tuple[PersonPose, ...] = ()) -> PoseFrame:
    return PoseFrame(image_width=WIDTH, image_height=HEIGHT, persons=persons)


def _image() -> np.ndarray:
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


class ScriptedBackend:
    """TrackBackend fake: replays one scripted id-tuple per ``track`` call."""

    def __init__(self, scripts: list[tuple[int | None, ...]]) -> None:
        self._scripts = [tuple(script) for script in scripts]
        self.calls = 0
        self.seen: list[tuple[Any, ...]] = []

    def track(
        self, detections: tuple[tuple[float, float, float, float], ...], image: Any
    ) -> tuple[int | None, ...]:
        self.calls += 1
        self.seen.append(tuple(detections))
        if self.calls <= len(self._scripts):
            return self._scripts[self.calls - 1]
        return self._scripts[-1]


def _history(max_observations: int = 60) -> TrackHistory:
    return TrackHistory(TrackHistoryConfig(max_observations=max_observations))


def _drive(
    tracker: PoseTracker,
    history: TrackHistory,
    frame: PoseFrame,
    timestamp: float,
    camera_id: str = CAMERA_ID,
) -> tuple[Any, ...]:
    observations = tracked_frame_to_observations(
        tracker.update(frame, _image()), camera_id=camera_id, timestamp=timestamp
    )
    for obs in observations:
        history.append(obs)
    return observations


# --- simultaneous people / crossing (areas 1-2) ------------------------------


def test_two_people_simultaneous_histories_independent_bit_exact() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.81, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.62, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (1, 2)]))
    history = _history()
    first = _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.80, 0.0)
    person_b2 = _person((204.0, 102.0, 304.0, 252.0), 0.63, 100.0)
    second = _drive(tracker, history, _frame((person_a2, person_b2)), 1.0)
    snap_a = history.snapshot(CAMERA_ID, 1)
    snap_b = history.snapshot(CAMERA_ID, 2)
    assert snap_a == (first[0], second[0])
    assert snap_b == (first[1], second[1])
    assert [obs.bbox_xyxy for obs in snap_a] == [person_a.bbox_xyxy, person_a2.bbox_xyxy]
    assert [obs.bbox_xyxy for obs in snap_b] == [person_b.bbox_xyxy, person_b2.bbox_xyxy]
    assert [obs.detection_confidence for obs in snap_a] == [0.81, 0.80]
    assert [obs.detection_confidence for obs in snap_b] == [0.62, 0.63]
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 2))


def test_crossing_close_approach_histories_follow_backend_ids() -> None:
    left = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    right = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    crossed_left = _person((110.0, 60.0, 160.0, 160.0), 0.7, 0.0)
    crossed_right = _person((100.0, 55.0, 150.0, 155.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (1, 2)]))
    history = _history()
    _drive(tracker, history, _frame((left, right)), 0.0)
    _drive(tracker, history, _frame((crossed_left, crossed_right)), 1.0)
    snap_1 = history.snapshot(CAMERA_ID, 1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert [obs.bbox_xyxy for obs in snap_1] == [left.bbox_xyxy, crossed_left.bbox_xyxy]
    assert [obs.bbox_xyxy for obs in snap_2] == [right.bbox_xyxy, crossed_right.bbox_xyxy]
    assert all(obs.track_id == 1 for obs in snap_1)
    assert all(obs.track_id == 2 for obs in snap_2)


# --- disappearance / gap semantics (areas 3-5) --------------------------------


def test_disappearance_survivor_continues_no_fabrication() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (1,)]))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    before_b = history.snapshot(CAMERA_ID, 2)
    assert len(before_b) == 1
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.7, 0.0)
    _drive(tracker, history, _frame((person_a2,)), 1.0)
    assert history.snapshot(CAMERA_ID, 2) == before_b
    assert len(history.snapshot(CAMERA_ID, 1)) == 2
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 2))
    assert len(history) == 2


def test_gap_same_id_return_continues_single_history() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1,), (), (), (1,)]))
    history = _history()
    first = _drive(tracker, history, _frame((person_a,)), 0.0)
    _drive(tracker, history, _frame(()), 1.0)
    _drive(tracker, history, _frame(()), 2.0)
    person_a3 = _person((30.0, 26.0, 80.0, 126.0), 0.7, 0.0)
    last = _drive(tracker, history, _frame((person_a3,)), 3.0)
    snap = history.snapshot(CAMERA_ID, 1)
    assert snap == (first[0], last[0])
    assert [obs.timestamp for obs in snap] == [0.0, 3.0]
    assert history.keys() == ((CAMERA_ID, 1),)


def test_gap_different_id_return_forks_fresh_old_untouched() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.7, 0.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1,), (1,), (), (9,)]))
    history = _history()
    first = _drive(tracker, history, _frame((person_a,)), 0.0)
    second = _drive(tracker, history, _frame((person_a2,)), 1.0)
    _drive(tracker, history, _frame(()), 2.0)
    person_new = _person((40.0, 30.0, 90.0, 130.0), 0.7, 0.0)
    fresh = _drive(tracker, history, _frame((person_new,)), 3.0)
    assert history.snapshot(CAMERA_ID, 1) == (first[0], second[0])
    assert history.snapshot(CAMERA_ID, 9) == (fresh[0],)
    assert len(history.snapshot(CAMERA_ID, 9)) == 1
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 9))


# --- None + cross-camera (areas 6-7) ------------------------------------------


def test_none_ids_never_contaminate_histories() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, None), (None, 1), (None, None)]))
    history = _history()
    first = _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    assert first[1].track_id is None
    _drive(tracker, history, _frame((person_b, person_a)), 1.0)
    _drive(tracker, history, _frame((person_a, person_b)), 2.0)
    snap = history.snapshot(CAMERA_ID, 1)
    assert [obs.bbox_xyxy for obs in snap] == [person_a.bbox_xyxy, person_a.bbox_xyxy]
    assert all(obs.track_id == 1 for obs in snap)
    assert all(obs.bbox_xyxy != person_b.bbox_xyxy for obs in snap)
    assert history.keys() == ((CAMERA_ID, 1),)
    assert len(history) == 1


def test_same_numeric_id_across_cameras_isolated_both_directions() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    backend_a = ScriptedBackend([(5,), (5,)])
    backend_b = ScriptedBackend([(5,), (5,)])
    tracker_a = PoseTracker(backend=backend_a)
    tracker_b = PoseTracker(backend=backend_b)
    history = _history()
    obs_a0 = _drive(tracker_a, history, _frame((person_a,)), 0.0, camera_id="cam-a")
    obs_b0 = _drive(tracker_b, history, _frame((person_b,)), 0.0, camera_id="cam-b")
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.7, 0.0)
    person_b2 = _person((204.0, 102.0, 304.0, 252.0), 0.7, 100.0)
    obs_a1 = _drive(tracker_a, history, _frame((person_a2,)), 1.0, camera_id="cam-a")
    obs_b1 = _drive(tracker_b, history, _frame((person_b2,)), 1.0, camera_id="cam-b")
    assert history.snapshot("cam-a", 5) == (obs_a0[0], obs_a1[0])
    assert history.snapshot("cam-b", 5) == (obs_b0[0], obs_b1[0])
    assert all(obs.camera_id == "cam-a" for obs in history.snapshot("cam-a", 5))
    assert all(obs.camera_id == "cam-b" for obs in history.snapshot("cam-b", 5))
    assert history.keys() == (("cam-a", 5), ("cam-b", 5))


# --- expiry / zero-person (areas 8-9) ------------------------------------------


def test_expiring_one_track_leaves_others_bit_exact_and_recreates_fresh() -> None:
    history = _history()
    stale = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    fresh_a = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    fresh_b = _person((204.0, 102.0, 304.0, 252.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1,), (2,), (2,)]))
    _drive(tracker, history, _frame((stale,)), 0.0)
    first = _drive(tracker, history, _frame((fresh_a,)), 9.0)
    second = _drive(tracker, history, _frame((fresh_b,)), 10.0)
    before = history.snapshot(CAMERA_ID, 2)
    assert before == (first[0], second[0])
    expired = history.expire_stale(10.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_ID, 1),)
    assert history.snapshot(CAMERA_ID, 2) == before
    assert history.keys() == ((CAMERA_ID, 2),)
    revived = _person((50.0, 40.0, 100.0, 140.0), 0.7, 0.0)
    tracker_revive = PoseTracker(backend=ScriptedBackend([(1,)]))
    new_obs = _drive(tracker_revive, history, _frame((revived,)), 11.0)
    assert history.snapshot(CAMERA_ID, 1) == (new_obs[0],)
    assert history.keys() == ((CAMERA_ID, 2), (CAMERA_ID, 1))


def test_zero_person_frames_preserve_active_state() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    backend = ScriptedBackend([(1, 2), ()])
    tracker = PoseTracker(backend=backend)
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    before_a = history.snapshot(CAMERA_ID, 1)
    before_b = history.snapshot(CAMERA_ID, 2)
    empty = _drive(tracker, history, _frame(()), 1.0)
    assert empty == ()
    assert backend.calls == 2
    assert backend.seen[1] == ()
    assert history.snapshot(CAMERA_ID, 1) == before_a
    assert history.snapshot(CAMERA_ID, 2) == before_b
    assert history.keys() == ((CAMERA_ID, 1), (CAMERA_ID, 2))


# --- order swaps (area 10) ------------------------------------------------------


def test_order_swap_two_frames_identity_follows_ids() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (2, 1)]))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    person_b2 = _person((204.0, 102.0, 304.0, 252.0), 0.7, 100.0)
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.7, 0.0)
    _drive(tracker, history, _frame((person_b2, person_a2)), 1.0)
    snap_1 = history.snapshot(CAMERA_ID, 1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert [obs.bbox_xyxy for obs in snap_1] == [person_a.bbox_xyxy, person_a2.bbox_xyxy]
    assert [obs.bbox_xyxy for obs in snap_2] == [person_b.bbox_xyxy, person_b2.bbox_xyxy]


def test_adversarial_reorder_reverse_rotation_three_frames() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    person_c = _person((400.0, 50.0, 460.0, 200.0), 0.7, 200.0)
    scripts = [(1, 2, 3), (3, 2, 1), (2, 3, 1)]
    tracker = PoseTracker(backend=ScriptedBackend(scripts))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b, person_c)), 0.0)
    _drive(tracker, history, _frame((person_c, person_b, person_a)), 1.0)
    _drive(tracker, history, _frame((person_b, person_c, person_a)), 2.0)
    assert [obs.bbox_xyxy for obs in history.snapshot(CAMERA_ID, 1)] == [person_a.bbox_xyxy] * 3
    assert [obs.bbox_xyxy for obs in history.snapshot(CAMERA_ID, 2)] == [person_b.bbox_xyxy] * 3
    assert [obs.bbox_xyxy for obs in history.snapshot(CAMERA_ID, 3)] == [person_c.bbox_xyxy] * 3


# --- gap landing + determinism (areas 11-12) --------------------------------------


def test_gap_return_lands_only_in_backend_named_key() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (1,), (1, 2)]))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    person_a2 = _person((14.0, 22.0, 64.0, 122.0), 0.7, 0.0)
    _drive(tracker, history, _frame((person_a2,)), 1.0)
    frozen_a = history.snapshot(CAMERA_ID, 1)
    frozen_b = history.snapshot(CAMERA_ID, 2)
    person_a3 = _person((18.0, 24.0, 68.0, 124.0), 0.7, 0.0)
    person_b3 = _person((208.0, 104.0, 308.0, 254.0), 0.7, 100.0)
    returned = _drive(tracker, history, _frame((person_a3, person_b3)), 2.0)
    assert history.snapshot(CAMERA_ID, 1) == frozen_a + (returned[0],)
    assert history.snapshot(CAMERA_ID, 2) == frozen_b + (returned[1],)
    assert returned[1].bbox_xyxy == person_b3.bbox_xyxy
    assert len(history.snapshot(CAMERA_ID, 1)) == 3
    assert len(history.snapshot(CAMERA_ID, 2)) == 2


def test_determinism_identical_sequences_equal_snapshots() -> None:
    def run_once() -> TrackHistory:
        person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
        person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
        tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (2, 1), (1,), (1, 2)]))
        history = _history()
        _drive(tracker, history, _frame((person_a, person_b)), 0.0)
        _drive(tracker, history, _frame((person_b, person_a)), 1.0)
        _drive(tracker, history, _frame((person_a,)), 2.0)
        _drive(tracker, history, _frame((person_a, person_b)), 3.0)
        return history

    first_run = run_once()
    second_run = run_once()
    assert first_run.keys() == second_run.keys()
    for key in first_run.keys():
        assert first_run.snapshot(*key) == second_run.snapshot(*key)


# --- content attachment (area 13) + tracker pairing -------------------------------


def test_content_attachment_per_entry_edge_confidences() -> None:
    tiny = [0.0, 1e-6, 1e-3, 0.5, 1.0]
    person_zero = _person((10.0, 20.0, 60.0, 120.0), 0.0, 0.0, conf=1e-6)
    person_full = _person((200.0, 100.0, 300.0, 250.0), 1.0, 100.0, conf=0.999999)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2)]))
    history = _history()
    _drive(tracker, history, _frame((person_zero, person_full)), 0.0)
    snap_1 = history.snapshot(CAMERA_ID, 1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert snap_1[0].detection_confidence == 0.0
    assert snap_2[0].detection_confidence == 1.0
    assert [kp.confidence for kp in snap_1[0].keypoints] == [1e-6] * 17
    assert [kp.confidence for kp in snap_2[0].keypoints] == [0.999999] * 17
    assert snap_1[0].bbox_xyxy == person_zero.bbox_xyxy
    assert snap_2[0].bbox_xyxy == person_full.bbox_xyxy
    assert tiny[0] == 0.0


def test_missing_keypoint_person_no_content_swap() -> None:
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.4, 100.0, missing=(3, 4, 9))
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (2, 1)]))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    _drive(tracker, history, _frame((person_b, person_a)), 1.0)
    snap_1 = history.snapshot(CAMERA_ID, 1)
    snap_2 = history.snapshot(CAMERA_ID, 2)
    assert all(kp.present for obs in snap_1 for kp in obs.keypoints)
    assert [kp.present for kp in snap_2[0].keypoints] == [
        index not in (3, 4, 9) for index in range(17)
    ]
    assert [kp.present for kp in snap_2[1].keypoints] == [
        index not in (3, 4, 9) for index in range(17)
    ]
    assert all(kp.x is None and kp.y is None for kp in snap_2[0].keypoints[3:5])
    assert snap_2[0].keypoints[9].x is None
    assert snap_1[0].keypoints[3].x == 6.0
    assert snap_2[0].detection_confidence == 0.4


def test_tracker_index_wise_pairing_ignores_list_position() -> None:
    person_left = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_right = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(2, 1)]))
    tracked = tracker.update(_frame((person_left, person_right)), _image())
    assert tracked.persons[0].track_id == 2
    assert tracked.persons[0].person is person_left
    assert tracked.persons[1].track_id == 1
    assert tracked.persons[1].person is person_right
    history = _history()
    for obs in tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=0.0):
        history.append(obs)
    assert history.snapshot(CAMERA_ID, 2)[0].bbox_xyxy == person_left.bbox_xyxy
    assert history.snapshot(CAMERA_ID, 1)[0].bbox_xyxy == person_right.bbox_xyxy


# --- framework-freedom proofs ------------------------------------------------------


def test_runtime_free_of_frameworks() -> None:
    before = set(sys.modules)
    person_a = _person((10.0, 20.0, 60.0, 120.0), 0.7, 0.0)
    person_b = _person((200.0, 100.0, 300.0, 250.0), 0.7, 100.0)
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2), (2, 1)]))
    history = _history()
    _drive(tracker, history, _frame((person_a, person_b)), 0.0)
    _drive(tracker, history, _frame((person_b, person_a)), 1.0)
    history.expire_stale(2.0, max_idle_seconds=5.0)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"tracking path loaded forbidden module: {module}"
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


def _module_level_roots(tree: ast.Module) -> list[str]:
    roots: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
    return roots


def _all_roots(tree: ast.Module) -> list[str]:
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
    return roots


def test_ast_no_framework_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    strict = [
        repo_root / "src" / "eldercare" / "vision" / "tracking" / "observation.py",
        repo_root / "src" / "eldercare" / "vision" / "tracking" / "history.py",
        Path(__file__),
    ]
    for target in strict:
        tree = ast.parse(target.read_text(encoding="utf-8"))
        roots = _all_roots(tree)
        if target.name != Path(__file__).name:
            assert roots, f"scanner found no imports at all in {target.name} (vacuous scan)"
        assert not [root for root in roots if root in _FORBIDDEN_RUNTIME_MODULES], (
            f"forbidden import in {target.name}: {roots}"
        )
    # tracker.py keeps ONE lazy method-level ``ultralytics`` import by design
    # (P3-001 record: test_lazy_import_only_inside_backend_method_ast) —
    # so only module-level roots are scanned here; strict full-walk applies
    # to observation.py / history.py / this test module.
    tracker_path = repo_root / "src" / "eldercare" / "vision" / "tracking" / "tracker.py"
    tracker_tree = ast.parse(tracker_path.read_text(encoding="utf-8"))
    module_roots = _module_level_roots(tracker_tree)
    assert module_roots, "scanner found no module-level imports in tracker.py (vacuous scan)"
    assert not [root for root in module_roots if root in _FORBIDDEN_RUNTIME_MODULES], (
        f"forbidden module-level import in tracker.py: {module_roots}"
    )
