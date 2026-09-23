"""Unit tests for the pose pipeline (P2-004).

TDD RED-first suite. CPU-only: synthetic ``np.zeros`` frames + duck-typed
stub ``Results`` (numpy arrays or pure nested lists). Neither this module nor
the pipeline may import ultralytics/torch/cv2 at runtime — proven by the
``sys.modules`` test and by the repo-wide grep in the task report.
"""

from __future__ import annotations

import logging
import math
import sys
from typing import Any

import numpy as np
import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT
from eldercare.vision.pose.pipeline import PosePipeline, PosePipelineResult, SourceFrame
from eldercare.vision.stream.queue import LatestFrameQueue

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


class FakePredictor:
    """PosePredictor fake: returns a fixed stub ``Results`` per call."""

    def __init__(self, results: Any) -> None:
        self._results = results
        self.calls = 0

    def predict(self, image: Any) -> Any:
        self.calls += 1
        return self._results


class ExplodingPredictor:
    """PosePredictor fake that fails the test if ever called."""

    def predict(self, image: Any) -> Any:
        raise AssertionError("predictor must not be called on read failure")


class FakeClock:
    """Deterministic clock (no real time, no sleeps)."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# --- synthetic fixtures --------------------------------------------------------


def _zero_image(height: int = 480, width: int = 640) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _one_person_xy() -> np.ndarray:
    return np.arange(34, dtype=np.float64).reshape(1, 17, 2)


def _one_person_conf() -> np.ndarray:
    return np.linspace(0.0, 1.0, num=17, dtype=np.float64).reshape(1, 17)


def _one_person_results() -> StubResults:
    return StubResults(
        StubKeypoints(_one_person_xy(), _one_person_conf()),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.77])),
        (480, 640),
    )


def _three_person_results() -> StubResults:
    n = 3
    xy = np.arange(n * 17 * 2, dtype=np.float64).reshape(n, 17, 2)
    conf = np.linspace(0.0, 1.0, num=n * 17, dtype=np.float64).reshape(n, 17)
    boxes = np.array(
        [[10.0 * (i + 1), 20.0, 10.0 * (i + 1) + 50.0, 120.0] for i in range(n)],
        dtype=np.float64,
    )
    box_conf = np.array([0.9 - 0.05 * i for i in range(n)], dtype=np.float64)
    return StubResults(StubKeypoints(xy, conf), StubBoxes(boxes, box_conf), (480, 640))


def _make_frame(**overrides: Any) -> SourceFrame:
    kwargs: dict[str, Any] = {
        "camera_id": "cam-01",
        "frame_id": 7,
        "capture_timestamp": 1000.0,
        "image": _zero_image(),
    }
    kwargs.update(overrides)
    return SourceFrame(**kwargs)


def _make_pipeline(
    results: Any = None, camera_id: str = "cam-01", clock: Any = None
) -> tuple[PosePipeline, FakePredictor]:
    predictor = FakePredictor(_one_person_results() if results is None else results)
    pipeline = PosePipeline(
        camera_id=camera_id, predictor=predictor, clock=FakeClock() if clock is None else clock
    )
    return pipeline, predictor


# --- SourceFrame / PosePipelineResult validation --------------------------------


def test_sourceframe_rejects_empty_camera_id() -> None:
    with pytest.raises(ValueError, match="camera_id"):
        _make_frame(camera_id="")


@pytest.mark.parametrize("bad_id", [None, 123, b"cam-01"])
def test_sourceframe_rejects_non_string_camera_id(bad_id: Any) -> None:
    with pytest.raises(TypeError, match="camera_id"):
        _make_frame(camera_id=bad_id)


@pytest.mark.parametrize("bad_id", [True, False])
def test_sourceframe_rejects_bool_frame_id(bad_id: Any) -> None:
    with pytest.raises(TypeError, match="frame_id"):
        _make_frame(frame_id=bad_id)


def test_sourceframe_rejects_negative_frame_id() -> None:
    with pytest.raises(ValueError, match="frame_id"):
        _make_frame(frame_id=-1)


@pytest.mark.parametrize("bad_id", ["7", 3.5, None])
def test_sourceframe_rejects_non_index_frame_id(bad_id: Any) -> None:
    with pytest.raises(TypeError, match="frame_id"):
        _make_frame(frame_id=bad_id)


@pytest.mark.parametrize("bad_ts", [math.nan, math.inf, -math.inf, -1.0, True])
def test_sourceframe_rejects_bad_timestamp(bad_ts: Any) -> None:
    with pytest.raises((ValueError, TypeError), match="[Tt]imestamp|capture_timestamp"):
        _make_frame(capture_timestamp=bad_ts)


@pytest.mark.parametrize("bad_image", [None, [[0, 0, 0]], "frame"])
def test_sourceframe_rejects_non_array_image(bad_image: Any) -> None:
    with pytest.raises(TypeError, match="[Ii]mage"):
        _make_frame(image=bad_image)


def test_sourceframe_rejects_non_3d_image() -> None:
    with pytest.raises(ValueError, match="[Ii]mage"):
        _make_frame(image=np.zeros((480, 640), dtype=np.uint8))


def test_sourceframe_rejects_empty_dim_image() -> None:
    with pytest.raises(ValueError, match="[Ii]mage"):
        _make_frame(image=np.zeros((0, 640, 3), dtype=np.uint8))


def test_sourceframe_rejects_non_uint8_image() -> None:
    with pytest.raises(TypeError, match="[Ii]mage|uint8|dtype"):
        _make_frame(image=np.zeros((480, 640, 3), dtype=np.float32))


def test_pipeline_result_rejects_non_poseframe_pose() -> None:
    with pytest.raises(TypeError, match="pose"):
        PosePipelineResult(
            camera_id="cam-01",
            frame_id=0,
            capture_timestamp=1.0,
            pose="not-a-pose",  # type: ignore[arg-type]
        )


def test_pipeline_rejects_bad_constructor_args() -> None:
    with pytest.raises(ValueError, match="camera_id"):
        PosePipeline(camera_id="", predictor=FakePredictor(_one_person_results()))
    with pytest.raises(TypeError, match="predictor"):
        PosePipeline(camera_id="cam-01", predictor=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="clock"):
        PosePipeline(
            camera_id="cam-01",
            predictor=FakePredictor(_one_person_results()),
            clock="x",  # type: ignore[arg-type]
        )


# --- process_frame: happy paths -------------------------------------------------


def test_process_frame_zero_person_dims_kept() -> None:
    pipeline, _ = _make_pipeline(StubResults(None, None, (480, 640)))
    result = pipeline.process_frame(_make_frame())
    assert isinstance(result, PosePipelineResult)
    assert result.pose.persons == ()
    assert (result.pose.image_width, result.pose.image_height) == (640, 480)


def test_process_frame_one_person_exact_values_numpy() -> None:
    pipeline, predictor = _make_pipeline()
    result = pipeline.process_frame(_make_frame())
    assert predictor.calls == 1
    assert len(result.pose.persons) == 1
    person = result.pose.persons[0]
    assert person.bbox_xyxy == (10.0, 20.0, 60.0, 120.0)
    assert person.detection_confidence == 0.77
    expected_xy = np.arange(34, dtype=np.float64).reshape(17, 2)
    expected_conf = np.linspace(0.0, 1.0, num=17, dtype=np.float64)
    assert len(person.keypoints) == KEYPOINT_COUNT
    for i, kp in enumerate(person.keypoints):
        assert kp.x == expected_xy[i, 0]
        assert kp.y == expected_xy[i, 1]
        assert kp.confidence == expected_conf[i]  # bit-for-bit: no rounding
        assert kp.present is True


def test_process_frame_one_person_pure_list_stubs() -> None:
    results = _one_person_results()
    list_results = StubResults(
        StubKeypoints(results.keypoints.xy.tolist(), results.keypoints.conf.tolist()),
        StubBoxes(results.boxes.xyxy.tolist(), results.boxes.conf.tolist()),
        [480, 640],
    )
    pipeline, _ = _make_pipeline(list_results)
    result = pipeline.process_frame(_make_frame())
    assert len(result.pose.persons) == 1
    assert result.pose.persons[0].detection_confidence == 0.77
    assert result.pose.persons[0].keypoints[0].x == 0.0
    assert result.pose.persons[0].keypoints[16].y == 33.0


def test_process_frame_three_person_ordering_and_conf() -> None:
    pipeline, _ = _make_pipeline(_three_person_results())
    result = pipeline.process_frame(_make_frame())
    assert len(result.pose.persons) == 3
    expected_conf = np.linspace(0.0, 1.0, num=51, dtype=np.float64).reshape(3, 17)
    for i, person in enumerate(result.pose.persons):
        assert person.bbox_xyxy == (10.0 * (i + 1), 20.0, 10.0 * (i + 1) + 50.0, 120.0)
        assert person.detection_confidence == 0.9 - 0.05 * i
        assert person.keypoints[0].x == float(i * 34)
        for k, kp in enumerate(person.keypoints):
            assert kp.confidence == expected_conf[i, k]


def test_process_frame_missing_keypoint_passthrough() -> None:
    xy = _one_person_xy()
    xy[0, 4, 0] = math.nan
    conf = _one_person_conf()
    pipeline, _ = _make_pipeline(
        StubResults(
            StubKeypoints(xy, conf),
            StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.77])),
            (480, 640),
        )
    )
    result = pipeline.process_frame(_make_frame())
    kp = result.pose.persons[0].keypoints[4]
    assert (kp.x, kp.y, kp.present) == (None, None, False)
    assert kp.confidence == float(conf[0, 4])  # conf preserved even when missing
    assert result.pose.persons[0].keypoints[0].present is True


def test_process_frame_propagates_identity_exactly() -> None:
    pipeline, _ = _make_pipeline()
    result = pipeline.process_frame(_make_frame(frame_id=42, capture_timestamp=1234.5))
    assert result.camera_id == "cam-01"
    assert result.frame_id == 42
    assert result.capture_timestamp == 1234.5


def test_process_frame_rejects_camera_id_mismatch() -> None:
    pipeline, _ = _make_pipeline()
    with pytest.raises(ValueError, match="camera_id|[Mm]ismatch"):
        pipeline.process_frame(_make_frame(camera_id="cam-other"))


def test_process_frame_rejects_non_sourceframe() -> None:
    pipeline, _ = _make_pipeline()
    with pytest.raises(TypeError, match="SourceFrame"):
        pipeline.process_frame("not-a-frame")  # type: ignore[arg-type]


def test_process_frame_logs_one_structured_record(caplog: pytest.LogCaptureFixture) -> None:
    pipeline, _ = _make_pipeline()
    with caplog.at_level(logging.DEBUG, logger="eldercare"):
        pipeline.process_frame(_make_frame())
    pose_records = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "pose.frame_processed"
    ]
    assert len(pose_records) == 1
    assert pose_records[0].frame_id == 7


# --- process_frame: malformed inference results fail closed ----------------------


def test_process_frame_none_results_fails_closed() -> None:
    pipeline = PosePipeline(camera_id="cam-01", predictor=FakePredictor(None), clock=FakeClock())
    with pytest.raises(ValueError, match="[Rr]esults|None"):
        pipeline.process_frame(_make_frame())


def test_process_frame_orig_shape_mismatch_fails_closed() -> None:
    pipeline, _ = _make_pipeline(_one_person_results())  # orig_shape (480, 640)
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        pipeline.process_frame(_make_frame(image=_zero_image(240, 320)))


def test_process_frame_orig_shape_mismatch_names_both_shapes() -> None:
    pipeline, _ = _make_pipeline(_one_person_results())
    with pytest.raises(ValueError) as excinfo:
        pipeline.process_frame(_make_frame(image=_zero_image(240, 320)))
    message = str(excinfo.value)
    assert "480" in message and "640" in message
    assert "240" in message and "320" in message


def test_process_frame_wrong_keypoint_count_fails_closed() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 16, 2)), np.zeros((1, 16))),
        StubBoxes(np.zeros((1, 4)), np.zeros((1,))),
        (480, 640),
    )
    pipeline, _ = _make_pipeline(bad)
    with pytest.raises(ValueError, match="17"):
        pipeline.process_frame(_make_frame())


def test_process_frame_boxes_mismatch_fails_closed() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 17, 2)), np.zeros((1, 17))),
        StubBoxes(np.zeros((2, 4)), np.zeros((2,))),
        (480, 640),
    )
    pipeline, _ = _make_pipeline(bad)
    with pytest.raises(ValueError, match="[Mm]ismatch"):
        pipeline.process_frame(_make_frame())


def test_process_frame_nan_detection_conf_fails_closed() -> None:
    bad = StubResults(
        StubKeypoints(_one_person_xy(), _one_person_conf()),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([math.nan])),
        (480, 640),
    )
    pipeline, _ = _make_pipeline(bad)
    with pytest.raises(ValueError, match="[Cc]onfidence"):
        pipeline.process_frame(_make_frame())


def test_process_frame_adapter_error_carries_frame_context() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 16, 2)), np.zeros((1, 16))),
        StubBoxes(np.zeros((1, 4)), np.zeros((1,))),
        (480, 640),
    )
    pipeline, _ = _make_pipeline(bad)
    with pytest.raises(ValueError) as excinfo:
        pipeline.process_frame(_make_frame(frame_id=99))
    assert "99" in str(excinfo.value)


def test_predictor_errors_propagate_unwrapped() -> None:
    class _BoomPredictor:
        def predict(self, image: Any) -> Any:
            raise RuntimeError("model exploded")

    pipeline = PosePipeline(camera_id="cam-01", predictor=_BoomPredictor(), clock=FakeClock())
    with pytest.raises(RuntimeError, match="model exploded"):
        pipeline.process_frame(_make_frame())


# --- process_capture_read / process_queued_frame ----------------------------------


def test_process_capture_read_false_returns_none_without_fabricating() -> None:
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), clock=FakeClock())
    assert pipeline.process_capture_read(False, _zero_image(), frame_id=1) is None


def test_process_capture_read_none_image_returns_none_without_fabricating() -> None:
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), clock=FakeClock())
    assert pipeline.process_capture_read(True, None, frame_id=1) is None


def test_process_capture_read_ok_delegates_with_explicit_timestamp() -> None:
    pipeline, predictor = _make_pipeline()
    result = pipeline.process_capture_read(True, _zero_image(), frame_id=3, capture_timestamp=55.0)
    assert result is not None
    assert predictor.calls == 1
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == ("cam-01", 3, 55.0)
    assert len(result.pose.persons) == 1


def test_process_capture_read_none_timestamp_reads_clock() -> None:
    pipeline, _ = _make_pipeline()
    pipeline._clock = FakeClock(777.0)
    result = pipeline.process_capture_read(True, _zero_image(), frame_id=3)
    assert result is not None
    assert result.capture_timestamp == 777.0


def test_process_queued_frame_empty_returns_none() -> None:
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), clock=FakeClock())
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    assert pipeline.process_queued_frame(queue, frame_id=1, capture_timestamp=5.0) is None


def test_process_queued_frame_populated_propagates_ids() -> None:
    pipeline, _ = _make_pipeline()
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    queue.put(_zero_image())
    result = pipeline.process_queued_frame(queue, frame_id=9, capture_timestamp=4321.0)
    assert result is not None
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == ("cam-01", 9, 4321.0)
    assert len(result.pose.persons) == 1
    assert queue.depth == 0


# --- no-retention / framework-freedom / repr ---------------------------------------


def test_pipeline_holds_no_results_reference() -> None:
    pipeline, _ = _make_pipeline()
    frame = _make_frame()
    pipeline.process_frame(frame)
    pipeline.process_frame(frame)
    assert not any("Results" in key for key in vars(pipeline))
    assert not any("Results" in type(value).__name__ for value in vars(pipeline).values())


def test_double_call_leaves_no_state_growth() -> None:
    pipeline, _ = _make_pipeline()
    pipeline.process_frame(_make_frame())
    before = {key: value for key, value in vars(pipeline).items()}
    pipeline.process_frame(_make_frame())
    assert set(vars(pipeline)) == set(before)


def test_runtime_stays_free_of_frameworks() -> None:
    before = set(sys.modules)
    pipeline, _ = _make_pipeline(
        StubResults(
            StubKeypoints(
                [[[float(k * 2 + c) for c in range(2)] for k in range(17)]],
                [[float(k) / 17.0 for k in range(17)]],
            ),
            StubBoxes([[10.0, 20.0, 60.0, 120.0]], [0.5]),
            [480, 640],
        )
    )
    pipeline.process_frame(_make_frame())
    pipeline.process_capture_read(True, _zero_image(), frame_id=2, capture_timestamp=9.0)
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    queue.put(_zero_image())
    pipeline.process_queued_frame(queue, frame_id=3, capture_timestamp=10.0)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"pipeline loaded forbidden module: {module}"


def test_repr_carries_camera_id_only() -> None:
    pipeline, _ = _make_pipeline()
    text = repr(pipeline)
    assert "cam-01" in text
    assert "http" not in text and "rtsp" not in text.lower()
