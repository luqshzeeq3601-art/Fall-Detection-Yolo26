"""Unit tests for the pose-result adapter (P2-003).

TDD RED-first suite. Every ``Results`` input below is a synthetic in-process
stub (numpy arrays, nested lists, or torch-like duck-typed fakes built from
lists only). Neither this module nor the adapter may import
ultralytics/torch/cv2 at runtime — proven by the ``sys.modules`` test and by
the repo-wide grep in the task report.
"""

from __future__ import annotations

import math
import sys
from typing import Any

import numpy as np
import pytest

from eldercare.vision.pose.adapter import (
    KEYPOINT_COUNT,
    KEYPOINT_NAMES,
    Keypoint,
    PoseFrame,
    adapt_pose_results,
)

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")


# --- duck-typed fakes (same attribute surface the adapter reads) --------------


class StubKeypoints:
    """Stand-in for ultralytics ``Keypoints`` (``.xy`` (N,17,2), ``.conf`` (N,17))."""

    def __init__(self, xy: Any, conf: Any) -> None:
        self.xy = xy
        self.conf = conf


class StubBoxes:
    """Stand-in for ultralytics ``Boxes`` (``.xyxy`` (N,4), ``.conf`` (N,))."""

    def __init__(self, xyxy: Any, conf: Any) -> None:
        self.xyxy = xyxy
        self.conf = conf


class StubResults:
    """Stand-in for ultralytics ``Results`` (``.keypoints``/``.boxes``/``.orig_shape``)."""

    def __init__(self, keypoints: Any, boxes: Any, orig_shape: Any) -> None:
        self.keypoints = keypoints
        self.boxes = boxes
        self.orig_shape = orig_shape


class TorchLikeTensor:
    """Minimal torch-Tensor duck-type surface (``.tolist()`` only, built from lists)."""

    def __init__(self, data: Any) -> None:
        self._data = data

    def tolist(self) -> Any:
        return self._data


# --- deterministic synthetic fixtures (no weights, no downloads) --------------


def _one_person_xy() -> np.ndarray:
    return np.arange(34, dtype=np.float64).reshape(1, 17, 2)


def _one_person_conf() -> np.ndarray:
    return np.linspace(0.0, 1.0, num=17, dtype=np.float64).reshape(1, 17)


def _one_person_result() -> StubResults:
    return StubResults(
        StubKeypoints(_one_person_xy(), _one_person_conf()),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
        (480, 640),
    )


def _three_person_result() -> StubResults:
    n = 3
    xy = np.arange(n * 17 * 2, dtype=np.float64).reshape(n, 17, 2)
    conf = np.linspace(0.0, 1.0, num=n * 17, dtype=np.float64).reshape(n, 17)
    boxes = np.array(
        [[10.0 * (i + 1), 20.0, 10.0 * (i + 1) + 50.0, 120.0] for i in range(n)],
        dtype=np.float64,
    )
    box_conf = np.array([0.9 - 0.05 * i for i in range(n)], dtype=np.float64)
    return StubResults(StubKeypoints(xy, conf), StubBoxes(boxes, box_conf), (480, 640))


# --- area 1: zero-person contract ----------------------------------------------


def test_zero_person_keypoints_none_returns_empty_persons_dims_kept() -> None:
    frame = adapt_pose_results(StubResults(None, None, (480, 640)))
    assert isinstance(frame, PoseFrame)
    assert frame.persons == ()
    assert frame.image_width == 640
    assert frame.image_height == 480


def test_zero_person_keypoints_none_with_empty_boxes_still_empty() -> None:
    boxes = StubBoxes(np.zeros((0, 4)), np.zeros((0,)))
    frame = adapt_pose_results(StubResults(None, boxes, (1080, 810)))
    assert frame.persons == ()
    assert (frame.image_height, frame.image_width) == (1080, 810)


# --- area 2: one-person exact values, conf bit-for-bit (numpy + list) ---------


def test_one_person_exact_values_numpy() -> None:
    frame = adapt_pose_results(_one_person_result())
    assert len(frame.persons) == 1
    person = frame.persons[0]
    assert person.bbox_xyxy == (10.0, 20.0, 60.0, 120.0)
    assert person.detection_confidence == 0.9
    expected_xy = np.arange(34, dtype=np.float64).reshape(17, 2)
    expected_conf = np.linspace(0.0, 1.0, num=17, dtype=np.float64)
    assert len(person.keypoints) == 17
    for i, kp in enumerate(person.keypoints):
        assert kp.x == expected_xy[i, 0]
        assert kp.y == expected_xy[i, 1]
        assert kp.confidence == expected_conf[i]  # exact: no rounding/filtering
        assert kp.present is True


def test_one_person_exact_values_list_stubs() -> None:
    result = _one_person_result()
    list_result = StubResults(
        StubKeypoints(result.keypoints.xy.tolist(), result.keypoints.conf.tolist()),
        StubBoxes(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()),
        [480, 640],
    )
    frame = adapt_pose_results(list_result)
    assert len(frame.persons) == 1
    person = frame.persons[0]
    assert person.bbox_xyxy == (10.0, 20.0, 60.0, 120.0)
    assert person.detection_confidence == 0.9
    for i, kp in enumerate(person.keypoints):
        assert kp.x == float(i * 2)
        assert kp.y == float(i * 2 + 1)
        assert kp.present is True
    expected_conf = np.linspace(0.0, 1.0, num=17, dtype=np.float64)
    for i, kp in enumerate(person.keypoints):
        assert kp.confidence == expected_conf[i]


def test_one_person_torch_like_duck_typed_stubs() -> None:
    result = _one_person_result()
    torch_like = StubResults(
        StubKeypoints(
            TorchLikeTensor(result.keypoints.xy.tolist()),
            TorchLikeTensor(result.keypoints.conf.tolist()),
        ),
        StubBoxes(
            TorchLikeTensor(result.boxes.xyxy.tolist()),
            TorchLikeTensor(result.boxes.conf.tolist()),
        ),
        (480, 640),
    )
    frame = adapt_pose_results(torch_like)
    assert len(frame.persons) == 1
    assert frame.persons[0].keypoints[0].x == 0.0
    assert frame.persons[0].keypoints[16].y == 33.0
    assert frame.persons[0].detection_confidence == 0.9


# --- area 3: multi-person ordering + per-person conf ----------------------------


def test_three_person_ordering_and_per_person_conf() -> None:
    frame = adapt_pose_results(_three_person_result())
    assert len(frame.persons) == 3
    expected_conf = np.linspace(0.0, 1.0, num=51, dtype=np.float64).reshape(3, 17)
    for i, person in enumerate(frame.persons):
        assert person.bbox_xyxy == (10.0 * (i + 1), 20.0, 10.0 * (i + 1) + 50.0, 120.0)
        assert person.detection_confidence == 0.9 - 0.05 * i
        assert person.keypoints[0].x == float(i * 34)
        for k, kp in enumerate(person.keypoints):
            assert kp.confidence == expected_conf[i, k]


# --- area 4: missingness (non-finite coords; conf always preserved) ------------


def test_missing_nan_x_gives_absent_keypoint_conf_preserved() -> None:
    xy = _one_person_xy()
    xy[0, 3, 0] = math.nan
    frame = adapt_pose_results(
        StubResults(
            StubKeypoints(xy, _one_person_conf()),
            StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
            (480, 640),
        )
    )
    kp = frame.persons[0].keypoints[3]
    assert kp.present is False
    assert kp.x is None
    assert kp.y is None
    assert kp.confidence == float(np.linspace(0.0, 1.0, num=17)[3])
    assert frame.persons[0].keypoints[0].present is True


def test_missing_pos_inf_y_gives_absent_keypoint_conf_preserved() -> None:
    xy = _one_person_xy()
    xy[0, 5, 1] = math.inf
    conf = _one_person_conf()
    frame = adapt_pose_results(
        StubResults(
            StubKeypoints(xy, conf),
            StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
            (480, 640),
        )
    )
    kp = frame.persons[0].keypoints[5]
    assert (kp.x, kp.y, kp.present) == (None, None, False)
    assert kp.confidence == float(conf[0, 5])


def test_missing_mixed_neg_inf_and_nan_gives_absent_keypoints() -> None:
    xy = _one_person_xy()
    xy[0, 7, 0] = -math.inf
    xy[0, 7, 1] = 5.0
    xy[0, 9, 0] = 5.0
    xy[0, 9, 1] = math.nan
    conf = _one_person_conf()
    frame = adapt_pose_results(
        StubResults(
            StubKeypoints(xy, conf),
            StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
            (480, 640),
        )
    )
    for k in (7, 9):
        kp = frame.persons[0].keypoints[k]
        assert kp.present is False
        assert kp.x is None
        assert kp.y is None
        assert kp.confidence == float(conf[0, k])


# --- area 5: malformed inputs fail closed ---------------------------------------


@pytest.mark.parametrize("n_keypoints", [16, 18])
def test_wrong_keypoint_count_raises(n_keypoints: int) -> None:
    xy = np.zeros((1, n_keypoints, 2))
    conf = np.zeros((1, n_keypoints))
    result = StubResults(
        StubKeypoints(xy, conf),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
        (480, 640),
    )
    with pytest.raises(ValueError, match="17"):
        adapt_pose_results(result)


def test_xy_conf_person_count_mismatch_raises() -> None:
    result = StubResults(
        StubKeypoints(np.zeros((2, 17, 2)), np.zeros((1, 17))),
        StubBoxes(np.zeros((2, 4)), np.zeros((2,))),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        adapt_pose_results(result)


def test_xy_conf_inner_count_mismatch_raises() -> None:
    result = StubResults(
        StubKeypoints(np.zeros((1, 17, 2)), np.zeros((1, 16))),
        StubBoxes(np.zeros((1, 4)), np.zeros((1,))),
        (480, 640),
    )
    with pytest.raises(ValueError, match="17"):
        adapt_pose_results(result)


def test_boxes_person_count_mismatch_raises() -> None:
    result = StubResults(
        StubKeypoints(np.zeros((1, 17, 2)), np.zeros((1, 17))),
        StubBoxes(np.zeros((2, 4)), np.zeros((2,))),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        adapt_pose_results(result)


@pytest.mark.parametrize("bad_conf", [math.nan, math.inf, -math.inf, 1.5, -0.1])
def test_bad_detection_confidence_raises(bad_conf: float) -> None:
    result = StubResults(
        StubKeypoints(_one_person_xy(), _one_person_conf()),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([bad_conf])),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Cc]onfidence"):
        adapt_pose_results(result)


@pytest.mark.parametrize("bad_conf", [math.nan, math.inf, -math.inf])
def test_non_finite_keypoint_confidence_raises(bad_conf: float) -> None:
    conf = _one_person_conf()
    conf[0, 5] = bad_conf
    result = StubResults(
        StubKeypoints(_one_person_xy(), conf),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.9])),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Cc]onfidence"):
        adapt_pose_results(result)


@pytest.mark.parametrize("bad_box", [[60.0, 20.0, 10.0, 120.0], [10.0, 120.0, 60.0, 20.0]])
def test_bad_bbox_ordering_raises(bad_box: list[float]) -> None:
    result = StubResults(
        StubKeypoints(_one_person_xy(), _one_person_conf()),
        StubBoxes(np.array([bad_box]), np.array([0.9])),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Bb]box"):
        adapt_pose_results(result)


@pytest.mark.parametrize("bad_shape", [(0, 640), (480, -1), (480,), (), None])
def test_bad_image_dims_raise(bad_shape: Any) -> None:
    result = StubResults(_one_person_result().keypoints, _one_person_result().boxes, bad_shape)
    with pytest.raises(ValueError, match="[Dd]im|shape|size"):
        adapt_pose_results(result)


def test_missing_orig_shape_attr_raises() -> None:
    class _NoShape:
        keypoints = _one_person_result().keypoints
        boxes = _one_person_result().boxes

    with pytest.raises(ValueError, match="[Dd]im|shape|size|orig_shape"):
        adapt_pose_results(_NoShape())


def test_none_results_raises() -> None:
    with pytest.raises(ValueError, match="[Rr]esults|None"):
        adapt_pose_results(None)


# --- area 6: Keypoint present ⟺ coords invariant ---------------------------------


def test_keypoint_invariant_present_true_with_missing_coords_raises() -> None:
    with pytest.raises(ValueError, match="present"):
        Keypoint(x=None, y=None, confidence=0.5, present=True)


def test_keypoint_invariant_present_false_with_coords_raises() -> None:
    with pytest.raises(ValueError, match="present"):
        Keypoint(x=1.0, y=2.0, confidence=0.5, present=False)


def test_keypoint_invariant_partial_coords_raise() -> None:
    with pytest.raises(ValueError, match="present"):
        Keypoint(x=1.0, y=None, confidence=0.5, present=True)
    with pytest.raises(ValueError, match="present"):
        Keypoint(x=None, y=2.0, confidence=0.5, present=False)


def test_keypoint_valid_constructions_keep_confidence() -> None:
    present_kp = Keypoint(x=1.0, y=2.0, confidence=0.0, present=True)
    assert (present_kp.x, present_kp.y, present_kp.present) == (1.0, 2.0, True)
    missing_kp = Keypoint(x=None, y=None, confidence=0.73, present=False)
    assert missing_kp.confidence == 0.73


# --- area 7: framework-freedom ----------------------------------------------------


def test_pure_list_stubs_work_without_numpy_containers() -> None:
    xy = [[[float(p * 34 + k * 2 + c) for c in range(2)] for k in range(17)] for p in range(2)]
    conf = [[float(p * 17 + k) / 34.0 for k in range(17)] for p in range(2)]
    boxes = [[10.0, 20.0, 60.0, 120.0], [70.0, 30.0, 130.0, 150.0]]
    frame = adapt_pose_results(
        StubResults(StubKeypoints(xy, conf), StubBoxes(boxes, [0.8, 0.7]), (480, 640))
    )
    assert len(frame.persons) == 2
    assert frame.persons[0].keypoints[0].x == 0.0
    assert frame.persons[1].keypoints[16].y == 67.0
    assert frame.persons[1].detection_confidence == 0.7


def test_runtime_stays_free_of_frameworks() -> None:
    before = set(sys.modules)
    adapt_pose_results(_one_person_result())
    adapt_pose_results(StubResults(None, None, (480, 640)))
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"adapter loaded forbidden module: {module}"


# --- area 8: keypoint names --------------------------------------------------------


def test_keypoint_names_length_17_and_spot_check() -> None:
    assert KEYPOINT_COUNT == 17
    assert len(KEYPOINT_NAMES) == 17
    assert KEYPOINT_NAMES[0] == "nose"
    assert KEYPOINT_NAMES[-1] == "right_ankle"
    assert KEYPOINT_NAMES == (
        "nose",
        "left_eye",
        "right_eye",
        "left_ear",
        "right_ear",
        "left_shoulder",
        "right_shoulder",
        "left_elbow",
        "right_elbow",
        "left_wrist",
        "right_wrist",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
    )
