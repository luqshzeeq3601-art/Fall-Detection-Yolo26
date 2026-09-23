"""Unit tests for the TrackObservation domain contract (P3-002).

TDD RED-first suite. CPU-only: hand-built ``TrackedFrame`` objects, zero
sleeps. Neither this module nor the observation source may import
ultralytics/torch/cv2 at runtime — proven by the ``sys.modules`` test and
the AST import scans below (P2-006/P3-001 pattern).
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path
from typing import Any

import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint, PersonPose, PoseFrame
from eldercare.vision.tracking.observation import (
    TrackObservation,
    tracked_frame_to_observations,
)
from eldercare.vision.tracking.tracker import TrackedFrame, TrackedPerson

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

HEIGHT = 480
WIDTH = 640
CAMERA_ID = "cam-01"
TIMESTAMP = 12.5


# --- builders ---------------------------------------------------------------


def _keypoints(offset: float = 0.0) -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(
            x=offset + float(i * 2),
            y=offset + float(i * 2 + 1),
            confidence=0.1 + 0.01 * i,
            present=True,
        )
        for i in range(KEYPOINT_COUNT)
    )


def _person(
    bbox: tuple[float, float, float, float] = (10.0, 20.0, 60.0, 120.0),
    det_conf: float = 0.77,
    keypoints: tuple[Keypoint, ...] | None = None,
) -> PersonPose:
    return PersonPose(
        bbox_xyxy=bbox,
        detection_confidence=det_conf,
        keypoints=_keypoints() if keypoints is None else keypoints,
    )


def _tracked(
    entries: tuple[tuple[PersonPose, int | None], ...] = (),
    width: int = WIDTH,
    height: int = HEIGHT,
) -> TrackedFrame:
    return TrackedFrame(
        image_width=width,
        image_height=height,
        persons=tuple(TrackedPerson(person=p, track_id=t) for p, t in entries),
    )


def _observation(**overrides: Any) -> TrackObservation:
    kwargs: dict[str, Any] = {
        "camera_id": CAMERA_ID,
        "track_id": 7,
        "timestamp": TIMESTAMP,
        "bbox_xyxy": (10.0, 20.0, 60.0, 120.0),
        "detection_confidence": 0.77,
        "keypoints": _keypoints(),
        "image_width": WIDTH,
        "image_height": HEIGHT,
    }
    kwargs.update(overrides)
    return TrackObservation(**kwargs)


# --- schema construction ----------------------------------------------------


def test_valid_construction_preserves_all_fields() -> None:
    keypoints = _keypoints(offset=3.0)
    obs = _observation(
        camera_id="cam-09",
        track_id=42,
        timestamp=99.25,
        bbox_xyxy=(1.0, 2.0, 3.0, 4.0),
        detection_confidence=0.33,
        keypoints=keypoints,
        image_width=320,
        image_height=240,
    )
    assert obs.camera_id == "cam-09"
    assert obs.track_id == 42
    assert obs.timestamp == 99.25
    assert obs.bbox_xyxy == (1.0, 2.0, 3.0, 4.0)
    assert obs.detection_confidence == 0.33
    assert obs.keypoints == keypoints
    assert len(obs.keypoints) == KEYPOINT_COUNT
    assert (obs.image_width, obs.image_height) == (320, 240)


def test_exact_field_set_no_extra_fields() -> None:
    names = [field.name for field in dataclasses.fields(TrackObservation)]
    assert names == [
        "camera_id",
        "track_id",
        "timestamp",
        "bbox_xyxy",
        "detection_confidence",
        "keypoints",
        "image_width",
        "image_height",
    ]
    assert not hasattr(TrackObservation, "pose_confidence_summary")
    assert not hasattr(_observation(), "frame_id")


# --- conversion boundary ----------------------------------------------------


def test_conversion_single_person_bit_exact() -> None:
    keypoints = _keypoints()
    person = _person(det_conf=0.91, keypoints=keypoints)
    tracked = _tracked(((person, 5),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert obs.camera_id == CAMERA_ID
    assert obs.track_id == 5
    assert obs.timestamp == TIMESTAMP
    assert obs.bbox_xyxy == person.bbox_xyxy
    assert obs.detection_confidence == person.detection_confidence
    assert obs.keypoints == person.keypoints
    assert (obs.image_width, obs.image_height) == (WIDTH, HEIGHT)


def test_conversion_multi_person_preserves_order() -> None:
    first = _person(bbox=(0.0, 0.0, 10.0, 10.0), det_conf=0.5)
    second = _person(bbox=(20.0, 30.0, 40.0, 50.0), det_conf=0.6)
    third = _person(bbox=(100.0, 100.0, 200.0, 200.0), det_conf=0.7)
    tracked = _tracked(((first, 3), (second, 1), (third, 2)))
    observations = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert [obs.track_id for obs in observations] == [3, 1, 2]
    assert [obs.bbox_xyxy for obs in observations] == [
        first.bbox_xyxy,
        second.bbox_xyxy,
        third.bbox_xyxy,
    ]


def test_conversion_zero_person_returns_empty() -> None:
    tracked = _tracked(())
    assert tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=1.0) == ()


def test_track_id_none_explicit_end_to_end() -> None:
    person = _person()
    tracked = _tracked(((person, None),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert obs.track_id is None
    assert obs.bbox_xyxy == person.bbox_xyxy


def test_large_track_id_preserved() -> None:
    person = _person()
    big = 2**40
    tracked = _tracked(((person, big),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert obs.track_id == big
    assert _observation(track_id=big).track_id == big


def test_bbox_bit_exact() -> None:
    bbox = (0.5, 1.25, 639.75, 479.5)
    person = _person(bbox=bbox)
    tracked = _tracked(((person, 9),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert obs.bbox_xyxy == bbox
    for got, want in zip(obs.bbox_xyxy, bbox, strict=True):
        assert got == want


def test_keypoint_order_index_aligned() -> None:
    keypoints = _keypoints(offset=100.0)
    person = _person(keypoints=keypoints)
    tracked = _tracked(((person, 4),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert len(obs.keypoints) == KEYPOINT_COUNT
    for index, (got, want) in enumerate(zip(obs.keypoints, keypoints, strict=True)):
        assert (got.x, got.y) == (want.x, want.y) == (100.0 + index * 2, 100.0 + index * 2 + 1)
        assert got.present is True
    assert obs.keypoints[0].x == 100.0  # nose slot
    assert obs.keypoints[16].x == 132.0  # right-ankle slot


def test_keypoint_confidences_bit_exact_edge_values() -> None:
    keypoints = tuple(
        Keypoint(x=float(i), y=float(i + 1), confidence=conf, present=True)
        for i, conf in enumerate(
            [0.0, 1e-12, 0.3, 0.5, 0.999999, 1.0, 0.123456789] + [0.42] * (KEYPOINT_COUNT - 7)
        )
    )
    person = _person(keypoints=keypoints)
    tracked = _tracked(((person, 11),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert [kp.confidence for kp in obs.keypoints] == [kp.confidence for kp in keypoints]
    assert obs.keypoints[0].confidence == 0.0
    assert obs.keypoints[1].confidence == 1e-12
    assert obs.keypoints[5].confidence == 1.0


def test_missing_keypoints_pass_through() -> None:
    keypoints = list(_keypoints())
    keypoints[3] = Keypoint(x=None, y=None, confidence=0.05, present=False)
    keypoints[9] = Keypoint(x=None, y=None, confidence=0.0, present=False)
    person = _person(keypoints=tuple(keypoints))
    tracked = _tracked(((person, 8),))
    (obs,) = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert obs.keypoints[3].x is None and obs.keypoints[3].y is None
    assert obs.keypoints[3].present is False
    assert obs.keypoints[3].confidence == 0.05
    assert obs.keypoints[9].confidence == 0.0
    assert obs.keypoints[0].present is True


def test_camera_timestamp_dims_propagation() -> None:
    person = _person()
    tracked = _tracked(((person, 2),), width=1280, height=720)
    (obs,) = tracked_frame_to_observations(tracked, camera_id="door-cam", timestamp=0.0)
    assert obs.camera_id == "door-cam"
    assert obs.timestamp == 0.0
    assert (obs.image_width, obs.image_height) == (1280, 720)


def test_conversion_deterministic() -> None:
    person = _person()
    tracked = _tracked(((person, 6),))
    first = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    second = tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    assert first == second
    assert first[0] == second[0]


# --- fail-closed validation -------------------------------------------------


def test_rejects_bad_camera_id() -> None:
    for bad in (None, 123, b"cam", ""):
        with pytest.raises((TypeError, ValueError), match="camera_id"):
            _observation(camera_id=bad)
    with pytest.raises(TypeError, match="camera_id"):
        _observation(camera_id=None)
    with pytest.raises(ValueError, match="camera_id"):
        _observation(camera_id="")


def test_rejects_bad_track_id() -> None:
    for bad in (True, False, "7", 7.0, -1, -100):
        with pytest.raises((TypeError, ValueError), match="track_id"):
            _observation(track_id=bad)
    with pytest.raises(TypeError, match="track_id"):
        _observation(track_id=True)
    with pytest.raises(ValueError, match="track_id"):
        _observation(track_id=-1)


def test_rejects_bad_timestamp() -> None:
    for bad in (True, "12.5", None, float("nan"), float("inf"), float("-inf"), -0.5, -10):
        with pytest.raises((TypeError, ValueError), match="timestamp"):
            _observation(timestamp=bad)
    with pytest.raises(ValueError, match="timestamp"):
        _observation(timestamp=float("nan"))


def test_rejects_bad_bbox() -> None:
    for bad in (
        (0.0, 0.0, 10.0),  # too short
        (0.0, 0.0, 10.0, 10.0, 5.0),  # too long
        (10.0, 0.0, 5.0, 10.0),  # x1 > x2
        (0.0, 20.0, 10.0, 5.0),  # y1 > y2
        (float("nan"), 0.0, 1.0, 1.0),
        (0.0, float("inf"), 1.0, 1.0),
        (True, 0.0, 1.0, 1.0),
        "bbox",
    ):
        with pytest.raises((TypeError, ValueError), match="[Bb]box|bbox_xyxy"):
            _observation(bbox_xyxy=bad)


def test_rejects_bad_detection_confidence() -> None:
    for bad in (True, None, float("nan"), float("inf"), -0.1, 1.1, 2.0):
        with pytest.raises((TypeError, ValueError), match="[Cc]onfidence"):
            _observation(detection_confidence=bad)


def test_rejects_bad_keypoints() -> None:
    with pytest.raises(ValueError, match="[Kk]eypoint"):
        _observation(keypoints=_keypoints()[:16])
    with pytest.raises(ValueError, match="[Kk]eypoint"):
        _observation(keypoints=_keypoints() + _keypoints()[:1])
    with pytest.raises(TypeError, match="[Kk]eypoint"):
        _observation(keypoints=tuple({"x": 1} for _ in range(KEYPOINT_COUNT)))
    with pytest.raises(TypeError, match="[Kk]eypoint"):
        _observation(keypoints="not-keypoints")


def test_rejects_bad_dims() -> None:
    for bad_width, bad_height in ((0, HEIGHT), (WIDTH, 0), (-5, HEIGHT), (WIDTH, -1)):
        with pytest.raises(ValueError, match="[Dd]ims|image"):
            _observation(image_width=bad_width, image_height=bad_height)
    for bad in (True, "640", 640.5, None):
        with pytest.raises((TypeError, ValueError), match="[Dd]ims|image"):
            _observation(image_width=bad)
        with pytest.raises((TypeError, ValueError), match="[Dd]ims|image"):
            _observation(image_height=bad)


def test_rejects_non_trackedframe_and_missing_kwargs() -> None:
    person = _person()
    pose = PoseFrame(image_width=WIDTH, image_height=HEIGHT, persons=(person,))
    with pytest.raises(TypeError, match="[Tt]rackedFrame|tracked"):
        tracked_frame_to_observations(pose, camera_id=CAMERA_ID, timestamp=TIMESTAMP)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="[Tt]rackedFrame|tracked"):
        tracked_frame_to_observations(None, camera_id=CAMERA_ID, timestamp=TIMESTAMP)  # type: ignore[arg-type]
    tracked = _tracked(((person, 1),))
    with pytest.raises(TypeError):
        tracked_frame_to_observations(tracked, CAMERA_ID, TIMESTAMP)  # type: ignore[misc]
    with pytest.raises((TypeError, ValueError)):
        tracked_frame_to_observations(tracked, camera_id="", timestamp=TIMESTAMP)
    with pytest.raises((TypeError, ValueError)):
        tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=float("nan"))


def test_frozen_immutability() -> None:
    obs = _observation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.track_id = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.timestamp = 0.0  # type: ignore[misc]


# --- downstream-consumability proof (test-local grouping) -------------------


def test_consumer_grouping_uses_only_observation_fields() -> None:
    """Bounded per-(camera_id, track_id) grouping from TrackObservation fields alone."""
    first = _person(bbox=(0.0, 0.0, 10.0, 10.0))
    second = _person(bbox=(20.0, 20.0, 30.0, 30.0))
    frames = [
        _tracked(((first, 1), (second, 2))),
        _tracked(((first, 1), (second, 2))),
        _tracked(((first, 1), (second, None))),
    ]
    groups: dict[tuple[str, int | None], list[TrackObservation]] = {}
    for step, tracked in enumerate(frames):
        for obs in tracked_frame_to_observations(
            tracked, camera_id=CAMERA_ID, timestamp=float(step)
        ):
            groups.setdefault((obs.camera_id, obs.track_id), []).append(obs)
    assert set(groups) == {(CAMERA_ID, 1), (CAMERA_ID, 2), (CAMERA_ID, None)}
    assert [obs.timestamp for obs in groups[(CAMERA_ID, 1)]] == [0.0, 1.0, 2.0]
    assert len(groups[(CAMERA_ID, 2)]) == 2
    assert groups[(CAMERA_ID, None)][0].bbox_xyxy == second.bbox_xyxy


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


def test_runtime_free_of_frameworks() -> None:
    before = set(sys.modules)
    tracked = _tracked(((_person(), 1),))
    tracked_frame_to_observations(tracked, camera_id=CAMERA_ID, timestamp=TIMESTAMP)
    _observation()
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"observation path loaded forbidden module: {module}"


def test_ast_no_framework_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    obs_path = repo_root / "src" / "eldercare" / "vision" / "tracking" / "observation.py"
    sites = _import_sites(obs_path.read_text(encoding="utf-8"))
    assert sites, "scanner found no imports at all (vacuous scan)"
    assert not [site for site in sites if site[0] in ("torch", "ultralytics", "cv2")]
    module_level = [site for site in sites if not site[1]]
    assert not [site for site in module_level if site[0] in _FORBIDDEN_RUNTIME_MODULES]
