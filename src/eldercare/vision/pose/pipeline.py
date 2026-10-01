"""Synchronous pose pipeline: stream input → predictor → normalized pose (P2-004).

Data path (contract-first)::

    SourceFrame → PosePredictor.predict → adapt_pose_results → PosePipelineResult

``SourceFrame`` carries ``camera_id`` / ``frame_id`` / ``capture_timestamp`` +
the ``image`` (ARCHITECTURE §5 frame-observation mapping). ``decode_timestamp``
(the pipeline-entry instant) is deliberately NOT a separate field: the
timestamp the pipeline acts on is ``capture_timestamp``, and entry timing is
not a stored observation (recording this decision per the brief).

Cross-check: ``results.orig_shape`` (h, w) — as parsed by the adapter into
``PoseFrame.image_width`` / ``image_height`` — must equal
``frame.image.shape[0:2]``; any mismatch raises ``ValueError`` naming both
shapes (fail clearly on malformed inference output, never guess).

No-retention rule: the heavyweight inference output lives in a method-local
name only, is dropped via ``del`` immediately after adaptation, and is never
stored on ``self`` (``vars(pipeline)`` holds no such reference).

Threading ownership: the pipeline holds no lock and spawns no threads. A
single capture-loop thread owns the call sequence (per P1-007 §1); the
thread-safe handoff between producer and consumer remains ``LatestFrameQueue``.

Phase 3 handoff: track observation consumes ``pose.persons[i].keypoints`` +
per-keypoint confidences + ``bbox_xyxy``; no track IDs are assigned here.

Timing (P2-005): ``process_frame`` stamps only around ``predictor.predict``
+ ``adapt_pose_results`` into ``PosePipelineResult.timing`` (milliseconds;
see ``timing.py``). Two-boundary rule: ``clock`` (default
:func:`time.monotonic`) stamps OBSERVATIONS (``capture_timestamp``
default); ``timer`` (default :func:`time.perf_counter`) measures DURATIONS.
Each is injectable so tests control them independently; neither is ever used
for the other's purpose. Capture latency and queue waiting time are NOT
inference metrics and are never included. ``timing=None`` means unmeasured
(hand-constructed results only); every pipeline-produced success result
carries a real ``PoseTiming``. Timing is exposed via the result contract
only, never via logs.

Stdlib + numpy ONLY: this module never imports ultralytics/torch/cv2 (not even
lazily). Stream types are imported for typing ONLY under ``TYPE_CHECKING``.
"""

from __future__ import annotations

import math
import operator
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from eldercare.common.logger import get_logger
from eldercare.vision.pose.adapter import PoseFrame, adapt_pose_results
from eldercare.vision.pose.timing import PoseTiming, timings_from_stamps

if TYPE_CHECKING:  # typing only: zero runtime import cost, no stream changes
    from eldercare.vision.pose.inference import PosePredictor
    from eldercare.vision.stream.queue import LatestFrameQueue


def _check_camera_id(value: Any) -> str:
    """Validate a camera identity (non-empty string; pattern lives upstream)."""
    if not isinstance(value, str):
        raise TypeError(f"camera_id must be a non-empty string, got {value!r}")
    if not value:
        raise ValueError(f"camera_id must be a non-empty string, got {value!r}")
    return value


def _check_frame_id(value: Any) -> int:
    """Validate a frame sequence number (>= 0 int; bools rejected)."""
    if isinstance(value, bool):
        raise TypeError(f"frame_id must be an int >= 0, got bool {value!r}")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"frame_id must be an int >= 0, got {value!r}") from exc
    if result < 0:
        raise ValueError(f"frame_id must be an int >= 0, got {value!r}")
    return result


def _check_capture_timestamp(value: Any) -> float:
    """Validate a capture timestamp (finite float >= 0)."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"capture_timestamp must be a finite float >= 0, got {value!r}")
    return float(value)


def _check_image(value: Any) -> np.ndarray:
    """Validate a frame image (3-D HxWxC uint8 array; no pixel-value policy)."""
    if not isinstance(value, np.ndarray):
        raise TypeError(f"image must be a numpy.ndarray, got {type(value).__name__}")
    if value.ndim != 3:
        raise ValueError(f"image must be a 3-D HxWxC array, got ndim={value.ndim}")
    height, width, channels = (int(dim) for dim in value.shape)
    if height <= 0 or width <= 0 or channels <= 0:
        raise ValueError(f"image dims must all be positive, got shape={value.shape!r}")
    if value.dtype != np.dtype(np.uint8):
        raise TypeError(f"image dtype must be uint8, got {value.dtype}")
    return value


@dataclass(frozen=True)
class SourceFrame:
    """One observed frame entering the pose pipeline."""

    camera_id: str
    frame_id: int
    capture_timestamp: float
    image: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _check_camera_id(self.camera_id))
        object.__setattr__(self, "frame_id", _check_frame_id(self.frame_id))
        timestamp = _check_capture_timestamp(self.capture_timestamp)
        object.__setattr__(self, "capture_timestamp", timestamp)
        object.__setattr__(self, "image", _check_image(self.image))


@dataclass(frozen=True)
class PosePipelineResult:
    """Normalized pose output for one frame (no inference output, image, or URL).

    ``timing`` carries the inference durations (milliseconds) when this
    result was produced by :meth:`PosePipeline.process_frame`; ``None``
    means not measured (hand-constructed results only — never a
    pipeline-produced success result, never a fabricated zero).
    """

    camera_id: str
    frame_id: int
    capture_timestamp: float
    pose: PoseFrame
    timing: PoseTiming | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _check_camera_id(self.camera_id))
        object.__setattr__(self, "frame_id", _check_frame_id(self.frame_id))
        timestamp = _check_capture_timestamp(self.capture_timestamp)
        object.__setattr__(self, "capture_timestamp", timestamp)
        if not isinstance(self.pose, PoseFrame):
            raise TypeError(f"pose must be a PoseFrame, got {type(self.pose).__name__}")
        if self.timing is not None and not isinstance(self.timing, PoseTiming):
            raise TypeError(
                f"timing must be a PoseTiming or None, got {type(self.timing).__name__}"
            )


class PosePipeline:
    """Synchronous frame → pose converter owned by one camera.

    Owns NO capture/queue/health/telemetry objects — they are passed per call
    and treated read-only. Holds no lock and spawns no threads.

    Args:
        camera_id: Stable camera identity (non-empty string).
        predictor: ``PosePredictor`` implementation (production or fake).
        clock: Zero-argument seconds source used only when a caller omits
            ``capture_timestamp`` (defaults to :func:`time.monotonic`).
        timer: Zero-argument seconds source used only to measure durations
            around predict + adapt (defaults to :func:`time.perf_counter`).
            Separate from ``clock`` so tests control observations and
            durations independently.
    """

    def __init__(
        self,
        camera_id: str,
        predictor: PosePredictor,
        clock: Callable[[], float] = time.monotonic,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._camera_id = _check_camera_id(camera_id)
        if not callable(getattr(predictor, "predict", None)):
            raise TypeError(f"predictor must expose a callable predict method, got {predictor!r}")
        self._predictor = predictor
        if not callable(clock):
            raise TypeError(f"clock must be a zero-argument callable, got {clock!r}")
        self._clock = clock
        if not callable(timer):
            raise TypeError(f"timer must be a zero-argument callable, got {timer!r}")
        self._timer = timer
        self._logger = get_logger("vision", component="pose.pipeline", camera_id=camera_id)

    def process_frame(self, frame: SourceFrame) -> PosePipelineResult:
        """Convert one :class:`SourceFrame` into a normalized result.

        Calls ``predictor.predict(frame.image)`` → ``adapt_pose_results`` →
        wraps with the propagated ``camera_id`` / ``frame_id`` /
        ``capture_timestamp``. Adapter ``ValueError``s propagate with frame
        context added via ``raise ... from`` (never fabricated, never an
        empty result on error). Predictor exceptions propagate unwrapped.
        """
        if not isinstance(frame, SourceFrame):
            raise TypeError(f"frame must be a SourceFrame, got {type(frame).__name__}")
        if frame.camera_id != self._camera_id:
            raise ValueError(
                "camera_id mismatch: pipeline owns "
                f"{self._camera_id!r}, frame carries {frame.camera_id!r} "
                "(identity is never silently overwritten)"
            )
        t0 = self._timer()
        results = self._predictor.predict(frame.image)
        t1 = self._timer()
        try:
            pose = adapt_pose_results(results)
        except ValueError as exc:
            raise ValueError(
                "pose adaptation failed for "
                f"camera_id={self._camera_id!r} frame_id={frame.frame_id!r}: {exc}"
            ) from exc
        t2 = self._timer()
        timing = timings_from_stamps(t0, t1, t2)
        image_height, image_width = int(frame.image.shape[0]), int(frame.image.shape[1])
        if pose.image_height != image_height or pose.image_width != image_width:
            raw_shape = getattr(results, "orig_shape", None)
            raise ValueError(
                "orig_shape/image shape mismatch for "
                f"camera_id={self._camera_id!r} frame_id={frame.frame_id!r}: "
                f"results.orig_shape={raw_shape!r} "
                f"(parsed h={pose.image_height}, w={pose.image_width}) vs "
                f"image shape (h={image_height}, w={image_width})"
            )
        result = PosePipelineResult(
            camera_id=self._camera_id,
            frame_id=frame.frame_id,
            capture_timestamp=frame.capture_timestamp,
            pose=pose,
            timing=timing,
        )
        del results  # no-retention: inference output never stored on self
        self._logger.debug(
            "pose frame processed",
            extra={
                "event": "pose.frame_processed",
                "frame_id": frame.frame_id,
                "person_count": len(pose.persons),
            },
        )
        return result

    def process_capture_read(
        self,
        ok: bool,
        frame_image: Any | None,
        frame_id: int,
        capture_timestamp: float | None = None,
    ) -> PosePipelineResult | None:
        """Convert one ``RtspCapture.read``-style ``(ok, image)`` outcome.

        ``ok`` falsy or ``frame_image is None`` → ``None`` (a read failure is
        not a pose — never fabricate; the caller drives reconnect/health).
        Otherwise builds a :class:`SourceFrame` with this pipeline's
        ``camera_id`` and delegates to :meth:`process_frame`.
        ``capture_timestamp=None`` reads the injected ``clock()``.
        """
        if not ok or frame_image is None:
            return None
        if capture_timestamp is None:
            capture_timestamp = self._clock()
        frame = SourceFrame(
            camera_id=self._camera_id,
            frame_id=frame_id,
            capture_timestamp=capture_timestamp,
            image=frame_image,
        )
        return self.process_frame(frame)

    def process_queued_frame(
        self,
        queue: LatestFrameQueue[Any],
        frame_id: int,
        capture_timestamp: float | None = None,
    ) -> PosePipelineResult | None:
        """Pop one payload via the queue's public ``get()`` and process it.

        An empty queue (``get()`` → ``None``) → ``None`` (not an error).
        Otherwise the popped payload is the frame image (payloads are opaque
        frame arrays in this integration) and processing delegates via
        :meth:`process_capture_read`. Queue internals are never touched.
        """
        payload = queue.get()
        if payload is None:
            return None
        return self.process_capture_read(True, payload, frame_id, capture_timestamp)

    def __repr__(self) -> str:
        return f"PosePipeline(camera_id={self._camera_id!r})"
