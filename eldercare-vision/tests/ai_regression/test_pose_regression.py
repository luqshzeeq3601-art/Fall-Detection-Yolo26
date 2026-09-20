"""Pose cross-module regression layer (P2-006).

Pins the YOLO26s-Pose contracts established by P2-002 through P2-005 at the
WIRING level (adapter <-> pipeline <-> timing <-> production defaults) that
the isolated unit/integration suites do not protect.

CPU-only: synthetic arange/linspace stubs + fake predictor + programmed
FakeTimer (no-sleep pattern). NEVER imports ultralytics/torch/cv2 at runtime
(proven by the sys.modules test + the source-level import-absence test).
Zero real sleeps, no wall-clock assertions, no accuracy/perf expectations.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from eldercare.vision.pose.adapter import (
    KEYPOINT_COUNT,
    KEYPOINT_NAMES,
    adapt_pose_results,
)
from eldercare.vision.pose.inference import UltralyticsPosePredictor
from eldercare.vision.pose.pipeline import PosePipeline, SourceFrame
from eldercare.vision.pose.timing import PoseTiming

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

_EXPECTED_KEYPOINT_NAMES: tuple[str, ...] = (
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

# --- duck-typed fakes (same attribute surface the adapter reads) ----------------


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


class FakePredictor:
    """PosePredictor fake: returns a fixed stub ``Results`` per call."""

    def __init__(self, results: Any) -> None:
        self._results = results
        self.calls = 0

    def predict(self, image: Any) -> Any:
        self.calls += 1
        return self._results


class FakeTimer:
    """Programmed duration-clock: returns the next stamp per call (zero delays)."""

    def __init__(self, stamps: list[float]) -> None:
        self._stamps = list(stamps)
        self.calls = 0

    def __call__(self) -> float:
        if self.calls >= len(self._stamps):
            raise AssertionError("FakeTimer exhausted: test programmed too few stamps")
        value = self._stamps[self.calls]
        self.calls += 1
        return value


# --- golden fixtures (synthetic arange/linspace only; inline, no files) ---------
# GOLDEN_4P mirrors the P2-002 verified production record: xy=(4,17,2),
# conf=(4,17), orig_shape=(1080, 810), boxes (4,4) + conf (4,) — the CPU-safe
# stand-in for the real CUDA contract (4 persons, bus.jpg).


def _golden_4p_xy() -> np.ndarray:
    return np.arange(4 * 17 * 2, dtype=np.float64).reshape(4, 17, 2)


def _golden_4p_conf() -> np.ndarray:
    conf = np.linspace(0.0, 1.0, num=4 * 17, dtype=np.float64).reshape(4, 17)
    conf[2, 5] = 1e-6  # tiny-scale value: must survive bit-for-bit
    conf[3, 9] = 2.5e-6  # second tiny-scale value, other person
    return conf  # conf[0, 0] is exactly 0.0 from linspace


def _golden_4p_boxes() -> np.ndarray:
    return np.array(
        [
            [10.0, 20.0, 60.0, 120.0],
            [70.0, 30.0, 130.0, 150.0],
            [200.0, 100.0, 300.0, 250.0],
            [400.0, 500.0, 600.0, 700.0],
        ],
        dtype=np.float64,
    )


def _golden_4p_box_conf() -> np.ndarray:
    # Distinct per-person detection confs, incl. exact 0.0 and a tiny value.
    return np.array([0.93, 0.61, 0.0, 1e-6], dtype=np.float64)


def _golden_4p_results() -> StubResults:
    return StubResults(
        StubKeypoints(_golden_4p_xy(), _golden_4p_conf()),
        StubBoxes(_golden_4p_boxes(), _golden_4p_box_conf()),
        (1080, 810),
    )


def _one_person_results() -> StubResults:
    return StubResults(
        StubKeypoints(
            np.arange(34, dtype=np.float64).reshape(1, 17, 2),
            np.linspace(0.0, 1.0, num=17, dtype=np.float64).reshape(1, 17),
        ),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.77])),
        (480, 640),
    )


def _zero_person_results() -> StubResults:
    return StubResults(None, None, (480, 640))


def _golden_image(height: int, width: int) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _process(
    results: Any,
    height: int,
    width: int,
    stamps: list[float] | None = None,
    frame_id: int = 7,
) -> Any:
    timer = FakeTimer(stamps if stamps is not None else [100.0, 100.010, 100.025])
    pipeline = PosePipeline(camera_id="cam-01", predictor=FakePredictor(results), timer=timer)
    frame = SourceFrame(
        camera_id="cam-01",
        frame_id=frame_id,
        capture_timestamp=1000.0,
        image=_golden_image(height, width),
    )
    return pipeline.process_frame(frame)


# --- area 1: production reference (P2-002 record pinned in code defaults) -------


def test_production_predictor_defaults_match_p2002_record() -> None:
    predictor = UltralyticsPosePredictor()
    assert predictor.model_name == "yolo26s-pose.pt"
    assert predictor.device == 0
    assert predictor.imgsz == 640


def test_keypoint_names_full_coco_tuple_and_count() -> None:
    assert KEYPOINT_COUNT == 17
    assert KEYPOINT_NAMES == _EXPECTED_KEYPOINT_NAMES
    assert len(KEYPOINT_NAMES) == KEYPOINT_COUNT == 17


def test_golden_4p_stub_shapes_match_p2002_acceptance() -> None:
    results = _golden_4p_results()
    assert results.keypoints.xy.shape == (4, 17, 2)
    assert results.keypoints.conf.shape == (4, 17)
    assert results.boxes.xyxy.shape == (4, 4)
    assert results.boxes.conf.shape == (4,)
    assert results.orig_shape == (1080, 810)


# --- area 2: golden 4-person end-to-end ------------------------------------------


def test_golden_4p_adapter_order_dims_and_detection_confs() -> None:
    frame = adapt_pose_results(_golden_4p_results())
    assert len(frame.persons) == 4
    assert (frame.image_width, frame.image_height) == (810, 1080)
    expected_boxes = _golden_4p_boxes()
    expected_confs = _golden_4p_box_conf()
    for i, person in enumerate(frame.persons):
        assert person.bbox_xyxy == tuple(expected_boxes[i])
        assert person.detection_confidence == expected_confs[i]


def test_golden_4p_first_and_last_person_keypoints_bit_exact() -> None:
    frame = adapt_pose_results(_golden_4p_results())
    expected_xy = _golden_4p_xy()
    expected_conf = _golden_4p_conf()
    for person_idx in (0, 3):
        person = frame.persons[person_idx]
        assert len(person.keypoints) == 17
        for k, kp in enumerate(person.keypoints):
            assert kp.x == expected_xy[person_idx, k, 0]
            assert kp.y == expected_xy[person_idx, k, 1]
            assert kp.confidence == expected_conf[person_idx, k]
            assert kp.present is True


def test_golden_4p_pipeline_result_matches_adapter_result() -> None:
    adapted = adapt_pose_results(_golden_4p_results())
    result = _process(_golden_4p_results(), 1080, 810)
    assert result.pose == adapted
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == (
        "cam-01",
        7,
        1000.0,
    )


# --- area 3: zero/one-person cross-module ----------------------------------------


def test_zero_person_pipeline_empty_dims_kept_timing_exact() -> None:
    result = _process(_zero_person_results(), 480, 640)
    assert result.pose.persons == ()
    assert (result.pose.image_width, result.pose.image_height) == (640, 480)
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)


def test_one_person_pipeline_exact_bbox_conf_coords() -> None:
    result = _process(_one_person_results(), 480, 640)
    assert len(result.pose.persons) == 1
    person = result.pose.persons[0]
    assert person.bbox_xyxy == (10.0, 20.0, 60.0, 120.0)
    assert person.detection_confidence == 0.77
    expected_xy = np.arange(34, dtype=np.float64).reshape(17, 2)
    expected_conf = np.linspace(0.0, 1.0, num=17, dtype=np.float64)
    for i, kp in enumerate(person.keypoints):
        assert kp.x == expected_xy[i, 0]
        assert kp.y == expected_xy[i, 1]
        assert kp.confidence == expected_conf[i]
        assert kp.present is True


def test_one_person_pipeline_timing_rides_along_undisturbed() -> None:
    result = _process(_one_person_results(), 480, 640, stamps=[200.0, 200.005, 200.020])
    assert len(result.pose.persons) == 1
    assert result.pose.persons[0].keypoints[0].x == 0.0
    assert result.pose.persons[0].keypoints[16].y == 33.0
    assert result.timing == PoseTiming(predict_ms=5.0, adapt_ms=15.0, total_ms=20.0)


# --- area 4: confidence preservation incl. 0.0 and tiny values --------------------


def test_confidence_zero_and_tiny_survive_adapter_bit_exact() -> None:
    frame = adapt_pose_results(_golden_4p_results())
    assert frame.persons[0].keypoints[0].confidence == 0.0
    assert frame.persons[2].keypoints[5].confidence == 1e-6
    assert frame.persons[3].keypoints[9].confidence == 2.5e-6
    assert frame.persons[2].detection_confidence == 0.0
    assert frame.persons[3].detection_confidence == 1e-6


def test_confidence_zero_and_tiny_survive_pipeline_bit_exact() -> None:
    result = _process(_golden_4p_results(), 1080, 810)
    assert result.pose.persons[0].keypoints[0].confidence == 0.0
    assert result.pose.persons[2].keypoints[5].confidence == 1e-6
    assert result.pose.persons[3].keypoints[9].confidence == 2.5e-6
    assert result.pose.persons[2].detection_confidence == 0.0
    assert result.pose.persons[3].detection_confidence == 1e-6


# --- area 5: missingness at pipeline level (no fabrication across wiring) --------


def test_nan_inf_missingness_at_pipeline_level_conf_preserved() -> None:
    xy = _golden_4p_xy()
    xy[1, 3, 0] = math.nan
    xy[2, 7, 1] = math.inf
    xy[2, 8, 0] = -math.inf
    conf = _golden_4p_conf()
    result = _process(
        StubResults(
            StubKeypoints(xy, conf),
            StubBoxes(_golden_4p_boxes(), _golden_4p_box_conf()),
            (1080, 810),
        ),
        1080,
        810,
    )
    missing_a = result.pose.persons[1].keypoints[3]
    assert (missing_a.x, missing_a.y, missing_a.present) == (None, None, False)
    assert missing_a.confidence == conf[1, 3]
    for k in (7, 8):
        kp = result.pose.persons[2].keypoints[k]
        assert (kp.x, kp.y, kp.present) == (None, None, False)
        assert kp.confidence == conf[2, k]
    assert result.pose.persons[1].keypoints[0].present is True
    assert result.pose.persons[2].keypoints[0].present is True
    assert result.pose.persons[0].keypoints[3].present is True
    assert result.pose.persons[0].keypoints[3].x == xy[0, 3, 0]


# --- area 6: integrated fail-closed spot-checks -----------------------------------


def test_pipeline_fail_closed_wrong_keypoint_dim() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 16, 2)), np.zeros((1, 16))),
        StubBoxes(np.zeros((1, 4)), np.zeros((1,))),
        (480, 640),
    )
    with pytest.raises(ValueError, match="17"):
        _process(bad, 480, 640)


def test_pipeline_fail_closed_box_count_mismatch() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 17, 2)), np.zeros((1, 17))),
        StubBoxes(np.zeros((2, 4)), np.zeros((2,))),
        (480, 640),
    )
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        _process(bad, 480, 640)


# --- area 7: orig_shape (h, w) -> (width, height) normalization --------------------


def test_golden_orig_shape_normalized_to_width_height() -> None:
    result = _process(_golden_4p_results(), 1080, 810)
    assert (result.pose.image_width, result.pose.image_height) == (810, 1080)


def test_second_shape_normalized_to_width_height() -> None:
    result = _process(_one_person_results(), 480, 640)
    assert (result.pose.image_width, result.pose.image_height) == (640, 480)


# --- area 8: timing non-interference -------------------------------------------------


def test_timing_non_interference_default_vs_programmed_timer() -> None:
    stub = _golden_4p_results()
    frame = SourceFrame(
        camera_id="cam-01",
        frame_id=7,
        capture_timestamp=1000.0,
        image=_golden_image(1080, 810),
    )
    default_pipeline = PosePipeline(camera_id="cam-01", predictor=FakePredictor(stub))
    timed_pipeline = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(stub),
        timer=FakeTimer([100.0, 100.010, 100.025]),
    )
    default_result = default_pipeline.process_frame(frame)
    timed_result = timed_pipeline.process_frame(frame)
    assert default_result.pose == timed_result.pose
    assert default_result.camera_id == timed_result.camera_id
    assert default_result.frame_id == timed_result.frame_id
    assert default_result.capture_timestamp == timed_result.capture_timestamp


# --- area 9: determinism ---------------------------------------------------------------


def test_determinism_repeat_calls_equal_pose_tree() -> None:
    stub = _golden_4p_results()
    frame = SourceFrame(
        camera_id="cam-01",
        frame_id=7,
        capture_timestamp=1000.0,
        image=_golden_image(1080, 810),
    )
    first = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(stub),
        timer=FakeTimer([100.0, 100.010, 100.025]),
    ).process_frame(frame)
    second = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(stub),
        timer=FakeTimer([100.0, 100.010, 100.025]),
    ).process_frame(frame)
    assert first.pose == second.pose


# --- area 10: framework independence ------------------------------------------------------


def test_sys_modules_free_across_golden_matrix_run() -> None:
    before = set(sys.modules)
    adapt_pose_results(_zero_person_results())
    adapt_pose_results(_one_person_results())
    adapt_pose_results(_golden_4p_results())
    _process(_zero_person_results(), 480, 640)
    _process(_one_person_results(), 480, 640)
    _process(_golden_4p_results(), 1080, 810)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"regression path loaded forbidden module: {module}"
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


def test_source_imports_absent_in_adapter_timing_pipeline() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    import_pattern = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)")
    checked: list[str] = []
    for rel in (
        "src/eldercare/vision/pose/adapter.py",
        "src/eldercare/vision/pose/timing.py",
        "src/eldercare/vision/pose/pipeline.py",
    ):
        text = (repo_root / rel).read_text(encoding="utf-8")
        roots = import_pattern.findall(text)
        for root in roots:
            assert root.split(".")[0] not in _FORBIDDEN_RUNTIME_MODULES, (
                f"{rel} imports forbidden framework: {root}"
            )
        checked.append(rel)
    assert checked == [
        "src/eldercare/vision/pose/adapter.py",
        "src/eldercare/vision/pose/timing.py",
        "src/eldercare/vision/pose/pipeline.py",
    ]


# --- area 11: manual-path separation (GPU/download path decoupled from pytest) -------


def test_manual_gpu_path_preserved_but_decoupled_from_pytest() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "dev" / "verify_pose_model.py"
    assert script.is_file()
    assert "tests" not in script.relative_to(repo_root).parts
    text = script.read_text(encoding="utf-8")
    assert "import pytest" not in text and "from pytest" not in text
    assert not re.search(r"(?m)^\s*def\s+test_", text)
