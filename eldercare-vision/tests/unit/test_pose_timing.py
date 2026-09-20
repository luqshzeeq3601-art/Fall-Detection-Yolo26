"""Unit tests for pose inference timing (P2-005).

TDD RED-first suite. CPU-only: synthetic ``np.zeros`` frames + duck-typed
stub ``Results`` (numpy arrays or pure nested lists) + programmed ``FakeTimer``
stamp sequences. Neither this module, the timing helper, nor the pipeline may
import ultralytics/torch/cv2 at runtime — proven by the ``sys.modules`` test
and by the repo-wide import sweep in the task report. Zero delays: every
duration comes from a programmed stamp sequence, never from waiting.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
from typing import Any

import numpy as np
import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT
from eldercare.vision.pose.pipeline import PosePipeline, PosePipelineResult, SourceFrame
from eldercare.vision.pose.timing import PoseTiming, timings_from_stamps
from eldercare.vision.stream.health import CameraHealthState, StreamHealthMonitor
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.stream.telemetry import CaptureTelemetry

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

_TIMING_VARS = {"_camera_id", "_predictor", "_clock", "_timer", "_logger"}


# --- fakes (CPU-only; pure-list stubs prove framework freedom) -----------------


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
    """Deterministic observation clock (no waiting)."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


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


class FakeCapture:
    """VideoCaptureLike-shaped fake: one frame, then ``(False, None)`` forever."""

    def __init__(self, frame: np.ndarray) -> None:
        self._frame = frame
        self._reads = 0

    def read(self) -> tuple[bool, np.ndarray | None]:
        self._reads += 1
        if self._reads == 1:
            return True, self._frame
        return False, None


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
    results: Any = None,
    camera_id: str = "cam-01",
    clock: Any = None,
    timer: Any = None,
) -> tuple[PosePipeline, FakePredictor]:
    predictor = FakePredictor(_one_person_results() if results is None else results)
    kwargs: dict[str, Any] = {
        "camera_id": camera_id,
        "predictor": predictor,
        "clock": FakeClock() if clock is None else clock,
    }
    if timer is not None:
        kwargs["timer"] = timer
    return PosePipeline(**kwargs), predictor


# --- PoseTiming validation -----------------------------------------------------


def test_timing_accepts_valid_triple() -> None:
    timing = PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)
    assert (timing.predict_ms, timing.adapt_ms, timing.total_ms) == (10.0, 15.0, 25.0)


def test_timing_to_dict_strict_json_round_trip() -> None:
    timing = PoseTiming(predict_ms=0.0, adapt_ms=4.5, total_ms=4.5)
    payload = timing.to_dict()
    assert payload == {"predict_ms": 0.0, "adapt_ms": 4.5, "total_ms": 4.5}
    assert all(type(value) is float for value in payload.values())
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


@pytest.mark.parametrize("field", ["predict_ms", "adapt_ms", "total_ms"])
@pytest.mark.parametrize("bad", [-1.0, -0.5, -math.inf])
def test_timing_rejects_negative_per_field(field: str, bad: float) -> None:
    base = {"predict_ms": 1.0, "adapt_ms": 2.0, "total_ms": 3.0}
    base[field] = bad
    with pytest.raises(ValueError, match=field):
        PoseTiming(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["predict_ms", "adapt_ms", "total_ms"])
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_timing_rejects_non_finite_per_field(field: str, bad: float) -> None:
    base = {"predict_ms": 1.0, "adapt_ms": 2.0, "total_ms": 3.0}
    base[field] = bad
    with pytest.raises(ValueError, match=field):
        PoseTiming(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["predict_ms", "adapt_ms", "total_ms"])
@pytest.mark.parametrize("bad", [True, False])
def test_timing_rejects_bool_per_field(field: str, bad: bool) -> None:
    base = {"predict_ms": 1.0, "adapt_ms": 2.0, "total_ms": 3.0}
    base[field] = bad
    with pytest.raises(ValueError, match=field):
        PoseTiming(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["predict_ms", "adapt_ms", "total_ms"])
@pytest.mark.parametrize("bad", ["1.0", None, object()])
def test_timing_rejects_non_numeric_per_field(field: str, bad: Any) -> None:
    base = {"predict_ms": 1.0, "adapt_ms": 2.0, "total_ms": 3.0}
    base[field] = bad
    with pytest.raises(ValueError, match=field):
        PoseTiming(**base)  # type: ignore[arg-type]


def test_timing_is_frozen() -> None:
    timing = PoseTiming(predict_ms=1.0, adapt_ms=2.0, total_ms=3.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        timing.predict_ms = 9.0  # type: ignore[misc]


# --- timings_from_stamps -------------------------------------------------------


def test_timings_from_stamps_exact_brief_vector() -> None:
    timing = timings_from_stamps(100.0, 100.010, 100.025)
    assert timing.predict_ms == 10.0
    assert timing.adapt_ms == 15.0
    assert timing.total_ms == 25.0
    assert timing.total_ms == timing.predict_ms + timing.adapt_ms


def test_timings_from_stamps_zero_duration_allowed() -> None:
    timing = timings_from_stamps(100.0, 100.0, 100.0)
    assert (timing.predict_ms, timing.adapt_ms, timing.total_ms) == (0.0, 0.0, 0.0)


def test_timings_from_stamps_separates_stages() -> None:
    timing = timings_from_stamps(50.0, 50.004, 50.010)
    assert timing.predict_ms == 4.0
    assert timing.adapt_ms == 6.0
    assert timing.total_ms == 10.0
    assert timing.predict_ms != timing.adapt_ms


def test_timings_from_stamps_rejects_backwards_predict() -> None:
    with pytest.raises(ValueError, match="t1.*t0|t0.*t1"):
        timings_from_stamps(100.0, 99.999, 100.025)


def test_timings_from_stamps_rejects_backwards_adapt() -> None:
    with pytest.raises(ValueError, match="t2.*t1|t1.*t2"):
        timings_from_stamps(100.0, 100.010, 100.005)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_timings_from_stamps_rejects_non_finite_t0(bad: float) -> None:
    with pytest.raises(ValueError, match="t0"):
        timings_from_stamps(bad, 100.010, 100.025)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_timings_from_stamps_rejects_non_finite_t1(bad: float) -> None:
    with pytest.raises(ValueError, match="t1"):
        timings_from_stamps(100.0, bad, 100.025)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_timings_from_stamps_rejects_non_finite_t2(bad: float) -> None:
    with pytest.raises(ValueError, match="t2"):
        timings_from_stamps(100.0, 100.010, bad)


@pytest.mark.parametrize("stamps", [(True, 100.010, 100.025), (100.0, False, 100.025)])
def test_timings_from_stamps_rejects_bool(stamps: tuple[Any, Any, Any]) -> None:
    with pytest.raises(ValueError, match="t[012]"):
        timings_from_stamps(*stamps)


def test_timing_units_are_milliseconds_not_seconds() -> None:
    timing = timings_from_stamps(100.0, 100.010, 100.010)
    assert timing.predict_ms == 10.0
    assert timing.predict_ms != 0.01
    assert timing.adapt_ms == 0.0
    assert timing.total_ms == 10.0


# --- pipeline integration: success paths ---------------------------------------


def test_process_frame_zero_person_carries_exact_timing() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(StubResults(None, None, (480, 640)), timer=timer)
    result = pipeline.process_frame(_make_frame())
    assert result.pose.persons == ()
    assert (result.pose.image_width, result.pose.image_height) == (640, 480)
    assert timer.calls == 3
    assert result.timing is not None
    assert (result.timing.predict_ms, result.timing.adapt_ms, result.timing.total_ms) == (
        10.0,
        15.0,
        25.0,
    )


def test_process_frame_one_person_exact_values_plus_timing() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, predictor = _make_pipeline(timer=timer)
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
        assert kp.confidence == expected_conf[i]
        assert kp.present is True
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)


def test_process_frame_three_person_ordering_conf_plus_timing() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(_three_person_results(), timer=timer)
    result = pipeline.process_frame(_make_frame())
    assert len(result.pose.persons) == 3
    expected_conf = np.linspace(0.0, 1.0, num=51, dtype=np.float64).reshape(3, 17)
    for i, person in enumerate(result.pose.persons):
        assert person.bbox_xyxy == (10.0 * (i + 1), 20.0, 10.0 * (i + 1) + 50.0, 120.0)
        assert person.detection_confidence == 0.9 - 0.05 * i
        assert person.keypoints[0].x == float(i * 34)
        for k, kp in enumerate(person.keypoints):
            assert kp.confidence == expected_conf[i, k]
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)


def test_process_frame_missing_keypoint_passthrough_keeps_timing() -> None:
    xy = _one_person_xy()
    xy[0, 4, 0] = math.nan
    conf = _one_person_conf()
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(
        StubResults(
            StubKeypoints(xy, conf),
            StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.77])),
            (480, 640),
        ),
        timer=timer,
    )
    result = pipeline.process_frame(_make_frame())
    kp = result.pose.persons[0].keypoints[4]
    assert (kp.x, kp.y, kp.present) == (None, None, False)
    assert kp.confidence == float(conf[0, 4])
    assert result.pose.persons[0].keypoints[0].present is True
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)


def test_repeated_calls_produce_fresh_timings_without_state_growth() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025, 200.0, 200.005, 200.020])
    pipeline, _ = _make_pipeline(timer=timer)
    assert set(vars(pipeline)) == _TIMING_VARS
    first = pipeline.process_frame(_make_frame())
    before = {key: value for key, value in vars(pipeline).items()}
    second = pipeline.process_frame(_make_frame())
    assert set(vars(pipeline)) == set(before) == _TIMING_VARS
    assert timer.calls == 6
    assert first.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)
    assert second.timing == PoseTiming(predict_ms=5.0, adapt_ms=15.0, total_ms=20.0)
    assert first.timing != second.timing


def test_process_capture_read_ok_carries_timing() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, predictor = _make_pipeline(timer=timer)
    result = pipeline.process_capture_read(True, _zero_image(), frame_id=3, capture_timestamp=55.0)
    assert result is not None
    assert predictor.calls == 1
    assert timer.calls == 3
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == ("cam-01", 3, 55.0)
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)


# --- pipeline integration: failure paths create no timing ----------------------


def test_predictor_error_propagates_with_single_stamp_consumed() -> None:
    class _BoomPredictor:
        def predict(self, image: Any) -> Any:
            raise RuntimeError("model exploded")

    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline = PosePipeline(camera_id="cam-01", predictor=_BoomPredictor(), timer=timer)
    with pytest.raises(RuntimeError, match="model exploded"):
        pipeline.process_frame(_make_frame())
    assert timer.calls == 1  # t0 only: no timing fabricated on predictor failure


def test_adapter_error_carries_frame_context_with_two_stamps_consumed() -> None:
    bad = StubResults(
        StubKeypoints(np.zeros((1, 16, 2)), np.zeros((1, 16))),
        StubBoxes(np.zeros((1, 4)), np.zeros((1,))),
        (480, 640),
    )
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(bad, timer=timer)
    with pytest.raises(ValueError) as excinfo:
        pipeline.process_frame(_make_frame(frame_id=99))
    assert "99" in str(excinfo.value)
    assert timer.calls == 2  # t0 + t1 only: no timing fabricated on adapt failure


def test_process_capture_read_false_returns_none_without_timer_use() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), timer=timer)
    assert pipeline.process_capture_read(False, _zero_image(), frame_id=1) is None
    assert timer.calls == 0


def test_process_capture_read_none_image_returns_none_without_timer_use() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), timer=timer)
    assert pipeline.process_capture_read(True, None, frame_id=1) is None
    assert timer.calls == 0


def test_process_queued_frame_empty_returns_none_without_timer_use() -> None:
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline = PosePipeline(camera_id="cam-01", predictor=ExplodingPredictor(), timer=timer)
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    assert pipeline.process_queued_frame(queue, frame_id=1, capture_timestamp=5.0) is None
    assert timer.calls == 0


def test_backwards_timer_stamps_fail_closed() -> None:
    timer = FakeTimer([100.010, 100.0, 100.025])  # t1 < t0: clock anomaly
    pipeline, _ = _make_pipeline(timer=timer)
    with pytest.raises(ValueError, match="t1.*t0|t0.*t1"):
        pipeline.process_frame(_make_frame())


# --- clock/timer independence --------------------------------------------------


def test_advancing_clock_alone_leaves_timing_unchanged() -> None:
    stamps = [100.0, 100.010, 100.025]
    early = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(_one_person_results()),
        clock=FakeClock(777.0),
        timer=FakeTimer(list(stamps)),
    )
    late = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(_one_person_results()),
        clock=FakeClock(888.0),
        timer=FakeTimer(list(stamps)),
    )
    first = early.process_capture_read(True, _zero_image(), frame_id=3)
    second = late.process_capture_read(True, _zero_image(), frame_id=3)
    assert first is not None and second is not None
    assert first.capture_timestamp == 777.0
    assert second.capture_timestamp == 888.0
    assert first.timing == second.timing == PoseTiming(10.0, 15.0, 25.0)


def test_advancing_timer_alone_leaves_observation_unchanged() -> None:
    clock = FakeClock(777.0)
    fast = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(_one_person_results()),
        clock=clock,
        timer=FakeTimer([100.0, 100.010, 100.025]),
    )
    slow = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(_one_person_results()),
        clock=clock,
        timer=FakeTimer([200.0, 200.005, 200.020]),
    )
    first = fast.process_capture_read(True, _zero_image(), frame_id=3)
    second = slow.process_capture_read(True, _zero_image(), frame_id=3)
    assert first is not None and second is not None
    assert first.capture_timestamp == second.capture_timestamp == 777.0
    assert (first.camera_id, first.frame_id) == (second.camera_id, second.frame_id)
    assert first.pose == second.pose
    assert first.timing == PoseTiming(10.0, 15.0, 25.0)
    assert second.timing == PoseTiming(5.0, 15.0, 20.0)


# --- contract regression -------------------------------------------------------


def test_default_timer_pipeline_matches_fake_timer_pose_fields() -> None:
    stub = _one_person_results()
    default_pipeline = PosePipeline(
        camera_id="cam-01", predictor=FakePredictor(stub), clock=FakeClock()
    )
    timed_pipeline, _ = _make_pipeline(stub, timer=FakeTimer([100.0, 100.010, 100.025]))
    frame = _make_frame()
    default_result = default_pipeline.process_frame(frame)
    timed_result = timed_pipeline.process_frame(frame)
    assert default_result.pose == timed_result.pose
    assert default_result.camera_id == timed_result.camera_id
    assert default_result.frame_id == timed_result.frame_id
    assert default_result.capture_timestamp == timed_result.capture_timestamp
    for result in (default_result, timed_result):
        assert isinstance(result.timing, PoseTiming)
        assert math.isfinite(result.timing.predict_ms)
        assert result.timing.predict_ms >= 0
        assert math.isfinite(result.timing.adapt_ms)
        assert result.timing.adapt_ms >= 0


def test_result_without_timing_defaults_to_none() -> None:
    result = PosePipelineResult(
        camera_id="cam-01",
        frame_id=0,
        capture_timestamp=1.0,
        pose=_make_pipeline()[0].process_frame(_make_frame()).pose,
    )
    assert result.timing is None


def test_result_rejects_non_timing() -> None:
    pose = _make_pipeline()[0].process_frame(_make_frame()).pose
    with pytest.raises(TypeError, match="timing"):
        PosePipelineResult(
            camera_id="cam-01",
            frame_id=0,
            capture_timestamp=1.0,
            pose=pose,
            timing="10ms",  # type: ignore[arg-type]
        )


def test_pipeline_rejects_non_callable_timer() -> None:
    predictor = FakePredictor(_one_person_results())
    for bad in ("x", 42, None):
        with pytest.raises(TypeError, match="timer"):
            PosePipeline(camera_id="cam-01", predictor=predictor, timer=bad)  # type: ignore[arg-type]


def test_process_frame_logs_one_structured_record_unchanged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(timer=timer)
    with caplog.at_level(logging.DEBUG, logger="eldercare"):
        pipeline.process_frame(_make_frame())
    pose_records = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "pose.frame_processed"
    ]
    assert len(pose_records) == 1
    assert pose_records[0].frame_id == 7
    assert pose_records[0].person_count == 1
    assert pose_records[0].getMessage() == "pose frame processed"


def test_repr_carries_camera_id_only() -> None:
    pipeline, _ = _make_pipeline(timer=FakeTimer([100.0, 100.010, 100.025]))
    text = repr(pipeline)
    assert "cam-01" in text
    assert "http" not in text and "rtsp" not in text.lower()


def test_runtime_stays_free_of_frameworks() -> None:
    before = set(sys.modules)
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline, _ = _make_pipeline(
        StubResults(
            StubKeypoints(
                [[[float(k * 2 + c) for c in range(2)] for k in range(17)]],
                [[float(k) / 17.0 for k in range(17)]],
            ),
            StubBoxes([[10.0, 20.0, 60.0, 120.0]], [0.5]),
            [480, 640],
        ),
        timer=timer,
    )
    result = pipeline.process_frame(_make_frame())
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"timed path loaded forbidden module: {module}"
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


# --- preservation: P2-004 fan-in rewired with a programmed timer ---------------


def test_fake_capture_fan_in_preserved_with_exact_timing() -> None:
    clock = FakeClock(1000.0)
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    telemetry = CaptureTelemetry(
        camera_id="cam-01", queue=queue, health=health, reconnect=None, clock=clock
    )
    timer = FakeTimer([100.0, 100.010, 100.025])
    pipeline = PosePipeline(
        camera_id="cam-01",
        predictor=FakePredictor(_one_person_results()),
        clock=clock,
        timer=timer,
    )
    capture = FakeCapture(np.zeros((480, 640, 3), dtype=np.uint8))

    assert health.state is CameraHealthState.UNKNOWN

    ok, frame = capture.read()
    assert ok is True
    assert frame is not None
    assert queue.put(frame) is False
    transition = health.notify_frame(1000.0)
    assert transition is not None
    assert transition.from_state is CameraHealthState.UNKNOWN
    assert transition.to_state is CameraHealthState.ONLINE
    telemetry.note_frame(1000.0)

    result = pipeline.process_queued_frame(queue, frame_id=7, capture_timestamp=1000.0)
    assert result is not None

    assert queue.submitted == 1
    assert queue.dropped == 0
    assert queue.depth == 0
    assert health.state is CameraHealthState.ONLINE
    assert health.last_frame_at == 1000.0
    assert telemetry.frames_received == 1
    snap = telemetry.snapshot(now=1000.0)
    assert snap.queue_submitted == 1
    assert snap.queue_dropped == 0
    assert snap.queue_depth == 0
    assert snap.health_state == "online"
    assert snap.last_frame_at == 1000.0
    assert snap.seconds_since_last_frame == 0.0
    assert snap.frames_received == 1
    json.dumps(snap.to_dict(), allow_nan=False)

    assert len(result.pose.persons) == 1
    person = result.pose.persons[0]
    assert len(person.keypoints) == 17
    assert (result.pose.image_width, result.pose.image_height) == (640, 480)
    assert person.detection_confidence == 0.77
    assert person.keypoints[0].x == 0.0
    assert person.keypoints[16].y == 33.0
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == (
        "cam-01",
        7,
        1000.0,
    )
    assert result.timing == PoseTiming(predict_ms=10.0, adapt_ms=15.0, total_ms=25.0)

    ok, frame = capture.read()
    assert (ok, frame) == (False, None)
