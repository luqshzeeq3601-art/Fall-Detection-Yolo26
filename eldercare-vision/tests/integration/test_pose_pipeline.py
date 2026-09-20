"""First integration test: fake capture → real queue/health/telemetry → pose (P2-004).

P1-007 gate precondition proved here: a fake capture is pumped end-to-end
through the REAL ``LatestFrameQueue`` + ``StreamHealthMonitor`` (fake clock) +
``CaptureTelemetry`` (fake clock) fan-in, then the queued payload runs through
a fake predictor + the real ``adapt_pose_results`` to the normalized
17-keypoint contract. Synchronous, no threads, no network, no sleeps.

CPU-only: synthetic ``np.zeros`` frames + stub ``Results``. Never imports
ultralytics/torch/cv2 — proven by the ``sys.modules`` test + grep.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np

from eldercare.vision.pose.pipeline import PosePipeline
from eldercare.vision.stream.health import CameraHealthState, StreamHealthMonitor
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.stream.telemetry import CaptureTelemetry

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

CAMERA_ID = "cam-01"
FRAME_ID = 7
TIMESTAMP = 1000.0
HEIGHT = 480
WIDTH = 640


class FakeClock:
    """Deterministic clock shared by health + telemetry (zero real sleeps)."""

    def __init__(self, now: float = TIMESTAMP) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


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
    """PosePredictor fake returning fixed stub ``Results`` (never touches weights)."""

    def __init__(self, results: Any) -> None:
        self._results = results

    def predict(self, image: Any) -> Any:
        return self._results


def _one_person_results() -> StubResults:
    xy = np.arange(34, dtype=np.float64).reshape(1, 17, 2)
    conf = np.linspace(0.0, 1.0, num=17, dtype=np.float64).reshape(1, 17)
    return StubResults(
        StubKeypoints(xy, conf),
        StubBoxes(np.array([[10.0, 20.0, 60.0, 120.0]]), np.array([0.77])),
        (HEIGHT, WIDTH),
    )


def _make_trio(
    clock: FakeClock,
) -> tuple[LatestFrameQueue[np.ndarray], StreamHealthMonitor, CaptureTelemetry]:
    queue: LatestFrameQueue[np.ndarray] = LatestFrameQueue(maxsize=2)
    health = StreamHealthMonitor(camera_id=CAMERA_ID, clock=clock)
    telemetry = CaptureTelemetry(
        camera_id=CAMERA_ID, queue=queue, health=health, reconnect=None, clock=clock
    )
    return queue, health, telemetry


def test_fake_capture_e2e_one_person() -> None:
    clock = FakeClock()
    queue, health, telemetry = _make_trio(clock)
    pipeline = PosePipeline(
        camera_id=CAMERA_ID, predictor=FakePredictor(_one_person_results()), clock=clock
    )
    capture = FakeCapture(np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))

    assert health.state is CameraHealthState.UNKNOWN

    # capture.read → queue.put → health.notify_frame → telemetry.note_frame ...
    ok, frame = capture.read()
    assert ok is True
    assert frame is not None
    assert queue.put(frame) is False  # no stale frame dropped
    transition = health.notify_frame(TIMESTAMP)
    assert transition is not None
    assert transition.from_state is CameraHealthState.UNKNOWN
    assert transition.to_state is CameraHealthState.ONLINE
    telemetry.note_frame(TIMESTAMP)

    # ... → pipeline.process_queued_frame → fake predictor → PoseFrame.
    result = pipeline.process_queued_frame(queue, frame_id=FRAME_ID, capture_timestamp=TIMESTAMP)
    assert result is not None

    # queue/health/telemetry fan-in exact assertions.
    assert queue.submitted == 1
    assert queue.dropped == 0
    assert queue.depth == 0  # payload popped by the pipeline
    assert health.state is CameraHealthState.ONLINE
    assert health.last_frame_at == TIMESTAMP
    assert telemetry.frames_received == 1
    snap = telemetry.snapshot(now=TIMESTAMP)
    assert snap.queue_submitted == 1
    assert snap.queue_dropped == 0
    assert snap.queue_depth == 0
    assert snap.health_state == "online"
    assert snap.last_frame_at == TIMESTAMP
    assert snap.seconds_since_last_frame == 0.0
    assert snap.capture_fps is None  # single frame is not a rate — never fabricated
    assert snap.frames_received == 1
    json.dumps(snap.to_dict(), allow_nan=False)  # strict-JSON-safe snapshot shape

    # normalized 17-keypoint contract assertions.
    assert len(result.pose.persons) == 1
    person = result.pose.persons[0]
    assert len(person.keypoints) == 17
    assert (result.pose.image_width, result.pose.image_height) == (WIDTH, HEIGHT)
    assert person.detection_confidence == 0.77
    assert person.keypoints[0].x == 0.0
    assert person.keypoints[16].y == 33.0
    assert (result.camera_id, result.frame_id, result.capture_timestamp) == (
        CAMERA_ID,
        FRAME_ID,
        TIMESTAMP,
    )


def test_fake_capture_e2e_zero_person() -> None:
    clock = FakeClock()
    queue, health, telemetry = _make_trio(clock)
    pipeline = PosePipeline(
        camera_id=CAMERA_ID,
        predictor=FakePredictor(StubResults(None, None, (HEIGHT, WIDTH))),
        clock=clock,
    )
    capture = FakeCapture(np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))

    ok, frame = capture.read()
    assert ok is True
    assert frame is not None
    queue.put(frame)
    assert health.notify_frame(TIMESTAMP) is not None
    telemetry.note_frame(TIMESTAMP)

    result = pipeline.process_queued_frame(queue, frame_id=FRAME_ID, capture_timestamp=TIMESTAMP)
    assert result is not None
    assert result.pose.persons == ()
    assert (result.pose.image_width, result.pose.image_height) == (WIDTH, HEIGHT)
    assert telemetry.frames_received == 1
    assert health.state is CameraHealthState.ONLINE

    # capture exhausted: read failure is not a pose.
    ok, frame = capture.read()
    assert (ok, frame) == (False, None)


def test_integration_stays_free_of_frameworks() -> None:
    before = set(sys.modules)
    clock = FakeClock()
    queue, _, _ = _make_trio(clock)
    queue.put(np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))
    pipeline = PosePipeline(
        camera_id=CAMERA_ID, predictor=FakePredictor(_one_person_results()), clock=clock
    )
    result = pipeline.process_queued_frame(queue, frame_id=1, capture_timestamp=TIMESTAMP)
    assert result is not None
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"integration path loaded forbidden module: {module}"
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules
