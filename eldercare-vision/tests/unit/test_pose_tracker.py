"""Unit tests for the ByteTrack pose-tracking boundary (P3-001).

TDD RED-first suite. CPU-only: hand-built ``PoseFrame`` objects + scripted
``TrackBackend`` fakes. Neither this module nor the tracking sources may import
ultralytics/torch/cv2 at runtime — proven by the ``sys.modules`` test, the
fresh-interpreter test, and the AST import scans below.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.tracker import (
    ByteTrackConfig,
    PoseTracker,
    TrackedFrame,
    TrackedPerson,
    UltralyticsByteTrackBackend,
    associate_detections_to_tracks,
    bbox_iou,
)

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

HEIGHT = 480
WIDTH = 640


# --- builders ---------------------------------------------------------------


def _keypoints() -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(x=float(i * 2), y=float(i * 2 + 1), confidence=0.1 + 0.01 * i, present=True)
        for i in range(17)
    )


def _person(
    bbox: tuple[float, float, float, float] = (10.0, 20.0, 60.0, 120.0),
    det_conf: float = 0.77,
) -> PersonPose:
    return PersonPose(bbox_xyxy=bbox, detection_confidence=det_conf, keypoints=_keypoints())


def _frame(persons: tuple[PersonPose, ...] = ()) -> PoseFrame:
    return PoseFrame(image_width=WIDTH, image_height=HEIGHT, persons=persons)


def _image(height: int = HEIGHT, width: int = WIDTH) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


class ScriptedBackend:
    """TrackBackend fake: replays one scripted id-tuple per ``track`` call."""

    def __init__(self, scripts: list[tuple[int | None, ...]]) -> None:
        self._scripts = [tuple(script) for script in scripts]
        self.calls: list[tuple[tuple[Any, ...], Any]] = []
        self.resets = 0

    def track(
        self, detections: tuple[tuple[float, float, float, float], ...], image: Any
    ) -> tuple[int | None, ...]:
        self.calls.append((tuple(detections), image))
        if not self._scripts:
            raise AssertionError("ScriptedBackend has no scripts left")
        if len(self.calls) <= len(self._scripts):
            return self._scripts[len(self.calls) - 1]
        return self._scripts[-1]

    def reset(self) -> None:
        self.resets += 1


class ExplodingBackend:
    """TrackBackend fake that fails the test if ever called."""

    def track(self, detections: Any, image: Any) -> tuple[int | None, ...]:
        raise AssertionError("backend must not be called")


# --- ByteTrackConfig --------------------------------------------------------


def test_config_defaults_select_stock_bytetrack() -> None:
    config = ByteTrackConfig()
    assert config.tracker == "bytetrack.yaml"
    assert config.persist is True


def test_config_rejects_bad_tracker() -> None:
    with pytest.raises(ValueError, match="tracker"):
        ByteTrackConfig(tracker="")
    with pytest.raises(TypeError, match="tracker"):
        ByteTrackConfig(tracker=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tracker"):
        ByteTrackConfig(tracker=123)  # type: ignore[arg-type]


def test_config_rejects_non_bool_persist() -> None:
    for bad in (1, 0, "yes", None):
        with pytest.raises(TypeError, match="persist"):
            ByteTrackConfig(persist=bad)  # type: ignore[arg-type]


def test_config_is_frozen() -> None:
    config = ByteTrackConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.tracker = "other.yaml"  # type: ignore[misc]


# --- PoseTracker: happy paths ----------------------------------------------


def test_first_frame_ids_from_backend() -> None:
    person = _person()
    backend = ScriptedBackend([(5,)])
    tracker = PoseTracker(backend=backend)
    tracked = tracker.update(_frame((person,)), _image())
    assert len(tracked.persons) == 1
    assert tracked.persons[0].track_id == 5
    assert len(backend.calls) == 1
    assert backend.calls[0][0] == (person.bbox_xyxy,)
    assert backend.calls[0][1] is not None


def test_stable_ids_across_sequential_frames() -> None:
    person = _person()
    backend = ScriptedBackend([(7,), (7,), (7,)])
    tracker = PoseTracker(backend=backend)
    ids = [tracker.update(_frame((person,)), _image()).persons[0].track_id for _ in range(3)]
    assert ids == [7, 7, 7]
    assert len(backend.calls) == 3


def test_multi_person_independent_ids() -> None:
    left = _person(bbox=(10.0, 20.0, 60.0, 120.0))
    right = _person(bbox=(200.0, 100.0, 300.0, 250.0))
    backend = ScriptedBackend([(3, 9), (3, 9)])
    tracker = PoseTracker(backend=backend)
    first = tracker.update(_frame((left, right)), _image())
    second = tracker.update(_frame((left, right)), _image())
    assert [p.track_id for p in first.persons] == [3, 9]
    assert [p.track_id for p in second.persons] == [3, 9]


def test_zero_person_empty_but_backend_consulted() -> None:
    backend = ScriptedBackend([()])
    tracker = PoseTracker(backend=backend)
    tracked = tracker.update(_frame(()), _image())
    assert tracked.persons == ()
    assert (tracked.image_width, tracked.image_height) == (WIDTH, HEIGHT)
    assert len(backend.calls) == 1  # tracker state ages honestly
    assert backend.calls[0][0] == ()


def test_disappearance_none_reappearance_passthrough() -> None:
    person = _person()
    backend = ScriptedBackend([(4,), (None,), (4,)])
    tracker = PoseTracker(backend=backend)
    ids = [tracker.update(_frame((person,)), _image()).persons[0].track_id for _ in range(3)]
    assert ids == [4, None, 4]  # our code never reuses or invents IDs


def test_persons_preserved_bit_exact_identity() -> None:
    left = _person(bbox=(10.0, 20.0, 60.0, 120.0), det_conf=0.61)
    right = _person(bbox=(200.0, 100.0, 300.0, 250.0), det_conf=0.93)
    backend = ScriptedBackend([(1, 2)])
    tracker = PoseTracker(backend=backend)
    tracked = tracker.update(_frame((left, right)), _image())
    assert tracked.persons[0].person is left
    assert tracked.persons[1].person is right
    assert tracked.persons[0].person.bbox_xyxy == (10.0, 20.0, 60.0, 120.0)
    assert tracked.persons[0].person.detection_confidence == 0.61
    assert tracked.persons[1].person.detection_confidence == 0.93
    assert tracked.persons[0].person.keypoints == left.keypoints


def test_unassigned_none_never_fabricated() -> None:
    persons = (_person(), _person(bbox=(200.0, 100.0, 300.0, 250.0)))
    backend = ScriptedBackend([(None, None)])
    tracker = PoseTracker(backend=backend)
    tracked = tracker.update(_frame(persons), _image())
    assert [p.track_id for p in tracked.persons] == [None, None]
    assert len(tracked.persons) == 2  # no filtering: persons survive unassigned


# --- PoseTracker: fail-closed ----------------------------------------------


def test_update_rejects_bad_frame() -> None:
    tracker = PoseTracker(backend=ScriptedBackend([()]))
    with pytest.raises(TypeError, match="[Pp]ose|[Ff]rame"):
        tracker.update(None, _image())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="[Pp]ose|[Ff]rame"):
        tracker.update("not-a-frame", _image())  # type: ignore[arg-type]


def test_update_rejects_bad_image() -> None:
    person = _person()
    tracker = PoseTracker(backend=ExplodingBackend())
    with pytest.raises(TypeError, match="[Ii]mage"):
        tracker.update(_frame((person,)), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="[Ii]mage"):
        tracker.update(_frame((person,)), np.zeros((HEIGHT, WIDTH), dtype=np.uint8))
    with pytest.raises(TypeError, match="[Ii]mage|uint8|dtype"):
        tracker.update(_frame((person,)), np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32))


def test_backend_count_mismatch_fails_closed() -> None:
    person = _person()
    tracker = PoseTracker(backend=ScriptedBackend([(1, 2)]))
    with pytest.raises(ValueError, match="[Mm]ismatch|[Cc]ount|[Ll]ength"):
        tracker.update(_frame((person,)), _image())
    tracker_short = PoseTracker(backend=ScriptedBackend([()]))
    with pytest.raises(ValueError, match="[Mm]ismatch|[Cc]ount|[Ll]ength"):
        tracker_short.update(_frame((person,)), _image())


def test_backend_bad_ids_fail_closed() -> None:
    person = _person()
    for bad_id, exc in [(True, TypeError), (-1, ValueError), ("3", TypeError), (2.5, TypeError)]:
        tracker = PoseTracker(backend=ScriptedBackend([(bad_id,)]))
        with pytest.raises(exc, match="[Tt]rack"):
            tracker.update(_frame((person,)), _image())


def test_backend_exception_propagates_unwrapped() -> None:
    class _BoomBackend:
        def track(self, detections: Any, image: Any) -> tuple[int | None, ...]:
            raise RuntimeError("tracker exploded")

    tracker = PoseTracker(backend=_BoomBackend())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="tracker exploded"):
        tracker.update(_frame((_person(),)), _image())


# --- IoU + greedy association helpers --------------------------------------


def test_iou_known_values() -> None:
    assert bbox_iou((0.0, 0.0, 10.0, 10.0), (0.0, 0.0, 10.0, 10.0)) == 1.0
    assert bbox_iou((0.0, 0.0, 10.0, 10.0), (20.0, 20.0, 30.0, 30.0)) == 0.0
    assert bbox_iou((0.0, 0.0, 10.0, 10.0), (5.0, 0.0, 15.0, 10.0)) == pytest.approx(1.0 / 3.0)
    assert bbox_iou((0.0, 0.0, 0.0, 10.0), (0.0, 0.0, 10.0, 10.0)) == 0.0


def test_association_greedy_rule_documented_cases() -> None:
    det_a = (0.0, 0.0, 10.0, 10.0)
    det_b = (100.0, 100.0, 110.0, 110.0)
    track_a = (1.0, 1.0, 11.0, 11.0)
    track_b = (101.0, 101.0, 111.0, 111.0)
    far = (500.0, 500.0, 510.0, 510.0)
    assert associate_detections_to_tracks((det_a, det_b), (track_a, track_b), (11, 22)) == (11, 22)
    # Unmatched detection -> None; unmatched track ignored; input order kept.
    assert associate_detections_to_tracks((det_a, far), (track_a, track_b), (11, 22)) == (11, None)
    assert associate_detections_to_tracks((det_a,), (track_a, track_b), (11, 22)) == (11,)
    # Each track claimed once: nearer detection wins, other degrades to None.
    assert associate_detections_to_tracks((det_a, det_a), (track_a,), (11,)) == (11, None)


def test_association_empty_inputs() -> None:
    assert associate_detections_to_tracks((), ((0.0, 0.0, 1.0, 1.0),), (9,)) == ()
    assert associate_detections_to_tracks(((0.0, 0.0, 1.0, 1.0),), (), ()) == (None,)


# --- reset + state bounds ---------------------------------------------------


def test_reset_contract() -> None:
    person = _person()
    backend = ScriptedBackend([(7,), (7,)])
    tracker = PoseTracker(backend=backend)
    assert tracker.update(_frame((person,)), _image()).persons[0].track_id == 7
    tracker.reset()
    assert backend.resets == 1
    assert tracker.update(_frame((person,)), _image()).persons[0].track_id == 7


def test_tracker_holds_no_unbounded_state() -> None:
    person = _person()
    backend = ScriptedBackend([(1,), (1,)])
    tracker = PoseTracker(backend=backend)
    tracker.update(_frame((person,)), _image())
    before = {key: value for key, value in vars(tracker).items()}
    tracker.update(_frame((person,)), _image())
    assert set(vars(tracker)) == set(before)
    assert set(vars(tracker)) == {"_config", "_backend"}


def test_tracker_rejects_bad_backend_and_uses_lazy_default() -> None:
    with pytest.raises(TypeError, match="[Bb]ackend|track"):
        PoseTracker(backend=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="[Cc]onfig"):
        PoseTracker(config="bytetrack.yaml")  # type: ignore[arg-type]
    tracker = PoseTracker()
    assert isinstance(tracker.backend, UltralyticsByteTrackBackend)
    assert "ultralytics" not in sys.modules  # default backend builds lazily


def test_production_backend_defaults_without_importing_framework() -> None:
    backend = UltralyticsByteTrackBackend()
    assert backend.model_name == "yolo26s-pose.pt"
    assert backend.config == ByteTrackConfig()
    assert "ultralytics" not in sys.modules
    assert "torch" not in sys.modules
    with pytest.raises(ValueError, match="model_name"):
        UltralyticsByteTrackBackend(model_name="")


# --- framework-freedom proofs ------------------------------------------------


def _import_sites(source: str) -> list[tuple[str, bool, str]]:
    """Every static import root plus whether it sits inside a function body."""
    tree = ast.parse(source)
    func_ranges = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    def _nested(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in func_ranges)

    sites: list[tuple[str, bool, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            sites.extend(
                (alias.name.split(".")[0], _nested(node.lineno), "import") for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                sites.append((node.module.split(".")[0], _nested(node.lineno), "from"))
    return sites


def test_lazy_import_only_inside_backend_method_ast() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tracker_path = repo_root / "src" / "eldercare" / "vision" / "tracking" / "tracker.py"
    tracker_source = tracker_path.read_text(encoding="utf-8")
    sites = _import_sites(tracker_source)
    assert sites, "scanner found no imports at all (vacuous scan)"
    assert not [site for site in sites if site[0] in ("torch", "cv2")]
    ultralytics_sites = [site for site in sites if site[0] == "ultralytics"]
    assert ultralytics_sites == [("ultralytics", True, "from")]  # one lazy method import
    module_level = [site for site in sites if not site[1]]
    assert not [site for site in module_level if site[0] in _FORBIDDEN_RUNTIME_MODULES]
    init_path = repo_root / "src" / "eldercare" / "vision" / "tracking" / "__init__.py"
    init_source = init_path.read_text(encoding="utf-8")
    init_roots = {site[0] for site in _import_sites(init_source)}
    assert init_roots, "scanner found no imports in __init__ (vacuous scan)"
    assert not (init_roots & set(_FORBIDDEN_RUNTIME_MODULES))


def test_runtime_stays_free_of_frameworks() -> None:
    before = set(sys.modules)
    person = _person()
    tracker = PoseTracker(backend=ScriptedBackend([(1,), (None,), ()]))
    tracker.update(_frame((person,)), _image())
    tracker.update(_frame((person,)), _image())
    tracker.update(_frame(()), _image())
    tracker.reset()
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"tracking path loaded forbidden module: {module}"
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


_FRESH_INTERPRETER_SCRIPT = """
import json
import sys

import numpy as np

from eldercare.vision.pose.adapter import Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.tracker import PoseTracker


class _Backend:
    def __init__(self):
        self.resets = 0

    def track(self, detections, image):
        return tuple(range(len(detections)))

    def reset(self):
        self.resets += 1


kps = tuple(Keypoint(x=1.0, y=2.0, confidence=0.5, present=True) for _ in range(17))
person = PersonPose(bbox_xyxy=(0.0, 0.0, 10.0, 10.0), detection_confidence=0.9, keypoints=kps)
tracker = PoseTracker(backend=_Backend())
frame = PoseFrame(image_width=640, image_height=480, persons=(person,))
assert tracker.update(frame, np.zeros((480, 640, 3), dtype=np.uint8)).persons[0].track_id == 0
tracker.reset()
print(json.dumps(sorted(m for m in ("torch", "ultralytics", "cv2") if m in sys.modules)))
"""


def test_forbidden_frameworks_absent_in_fresh_interpreter() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-c", _FRESH_INTERPRETER_SCRIPT],
        env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"fresh interpreter failed: {proc.stderr}"
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    assert loaded == [], f"tracking modules loaded forbidden frameworks: {loaded}"


def test_tracked_types_validation() -> None:
    person = _person()
    assert TrackedPerson(person=person, track_id=None).track_id is None
    assert TrackedPerson(person=person, track_id=0).track_id == 0
    with pytest.raises(TypeError, match="[Pp]erson"):
        TrackedPerson(person="x", track_id=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="[Tt]rack"):
        TrackedPerson(person=person, track_id=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="[Tt]rack"):
        TrackedPerson(person=person, track_id="1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="[Tt]rack"):
        TrackedPerson(person=person, track_id=-1)
    frame = TrackedFrame(
        image_width=WIDTH, image_height=HEIGHT, persons=(TrackedPerson(person, 2),)
    )
    assert isinstance(frame, TrackedFrame)
    assert frame.persons[0].track_id == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        frame.image_width = 1  # type: ignore[misc]
    with pytest.raises(ValueError, match="[Ii]mage|[Ww]idth|[Hh]eight"):
        TrackedFrame(image_width=0, image_height=HEIGHT, persons=())
    with pytest.raises(TypeError, match="[Pp]erson"):
        TrackedFrame(image_width=WIDTH, image_height=HEIGHT, persons=(person,))  # type: ignore[list-item]
