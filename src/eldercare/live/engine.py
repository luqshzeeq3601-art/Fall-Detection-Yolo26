"""Fall inference engine for YOLO26 pose estimation and the frozen V6.3 classifier.

Runs the frozen V6.3 pipeline (``models/v6_3_phase3b``): YOLO26s-pose with stock
ByteTrack, online track stitching, the M2 skeleton classifier and the calibrated
decision stage, on every tracked person at 15 Hz. Shared by the API live worker
and the Streamlit demo; the frozen classifier is loaded once per process.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.pipeline_v6_1 import (
    FallEnginePipelineV61,
    PipelineConfigV61,
    pipeline_config_from_calibration,
)
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from eldercare.fall_engine.track_stitching import OnlineTrackStitcher
from eldercare.vision.pose.adapter import adapt_pose_results
from eldercare.vision.tracking.observation import TrackObservation

LOG = logging.getLogger("eldercare.live.engine")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
FROZEN_MODEL_DIR = PROJECT_ROOT / "models" / "v6_3_phase3b"

_STATE_RANK = {
    FallState.NORMAL: 0,
    FallState.RECOVERY: 0,
    FallState.DESCENT_CANDIDATE: 1,
    FallState.DOWN_CONFIRMING: 2,
    FallState.FALL_CONFIRMED: 3,
}


@dataclass
class FrameInferenceResult:
    """Output metrics for a single processed video frame (most critical person)."""

    state: str  # "NORMAL", "FALLING", "FALL_DETECTED"
    confidence: float
    vertical_velocity: float
    aspect_ratio: float
    floor_proximity: float
    keypoints: np.ndarray | None
    bbox: tuple[int, int, int, int] | None
    track_id: int
    # Set only on the frame where the pipeline confirms a new fall for this track.
    fall_event: FallEvent | None = None


def pose_weights_path() -> Path | None:
    """First YOLO26s-pose weights file found, or None."""
    for p in (PROJECT_ROOT / "models" / "yolo26s-pose.pt", PROJECT_ROOT / "yolo26s-pose.pt"):
        if p.is_file():
            return p
    return None


def load_pose_model() -> Any | None:
    """Load a fresh YOLO26s-Pose model.

    Each live session needs its own instance: ``model.track(persist=True)`` keeps
    tracker state on the model object.
    """
    path = pose_weights_path()
    if path is None:
        return None
    try:
        from ultralytics import YOLO

        return YOLO(str(path))
    except Exception as e:  # noqa: BLE001 - reported as "model unavailable"
        LOG.warning("Failed to load model from %s: %s", path, e)
        return None


_FALL_MODEL_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _load_frozen_fall_model_cached() -> tuple[TemporalSkeletonClassifierV5, dict[str, Any]] | None:
    model_path = FROZEN_MODEL_DIR / "temporal_skeleton_classifier_v6.pt"
    report_path = FROZEN_MODEL_DIR / "v6_training_report.json"
    if not (model_path.is_file() and report_path.is_file()):
        LOG.warning("Frozen fall model not found in %s", FROZEN_MODEL_DIR)
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return TemporalSkeletonClassifierV5.load(model_path), report["calibrated_post_processor"]


def load_frozen_fall_model() -> tuple[TemporalSkeletonClassifierV5, dict[str, Any]] | None:
    """Frozen M2 classifier and its calibrated operating point, or None if missing."""
    with _FALL_MODEL_LOCK:
        return _load_frozen_fall_model_cached()


def frozen_operating_point() -> dict[str, Any]:
    """Calibrated decision thresholds of the frozen model (empty if unavailable)."""
    loaded = load_frozen_fall_model()
    return dict(loaded[1]) if loaded is not None else {}


class FallInferenceEngine:
    """Stateful per-track fall inference for demo clips and live feeds.

    ``fall_threshold`` and ``min_down_sec`` override the frozen kinetic trigger and
    sustain time (the sidebar sliders); ``None`` keeps the calibrated values.
    """

    def __init__(
        self,
        fall_threshold: float | None = None,
        min_down_sec: float | None = None,
        target_fps: float = 15.0,
    ) -> None:
        self.target_fps = target_fps
        self._last_t: float | None = None
        self._clock = 0.0
        self._last_result: FrameInferenceResult | None = None
        self._prev_hip_y: dict[int, float] = {}
        self._stitcher = OnlineTrackStitcher()
        self._pipeline: FallEnginePipelineV61 | None = None
        self._alerted: set[int] = set()

        loaded = load_frozen_fall_model()
        if loaded is not None:
            classifier, cal = loaded
            cfg: PipelineConfigV61 = pipeline_config_from_calibration(cal)
            pp = cfg.post_processor
            if fall_threshold is not None:
                pp = replace(pp, fall_trigger_threshold=fall_threshold)
            if min_down_sec is not None:
                pp = replace(pp, min_down_sustain_seconds=min_down_sec)
            self._pipeline = FallEnginePipelineV61(
                skeleton_classifier=classifier, config=replace(cfg, post_processor=pp)
            )

    @property
    def ready(self) -> bool:
        """True when the frozen fall classifier is loaded."""
        return self._pipeline is not None

    @property
    def last_inference_timestamp(self) -> float | None:
        """Source timestamp of the most recent frame that actually ran inference."""
        return self._last_t

    def reset(self) -> None:
        """Reset temporal state when switching videos."""
        self._last_t = None
        self._clock = 0.0
        self._last_result = None
        self._prev_hip_y.clear()
        self._stitcher.reset()
        self._alerted.clear()
        if self._pipeline is not None:
            self._pipeline.reset()

    def process_frame(
        self,
        frame: np.ndarray,
        model: Any | None,
        target_fps: float | None = None,
        timestamp: float | None = None,
    ) -> FrameInferenceResult:
        """Process one BGR frame; inference runs at most ``target_fps`` times per second.

        ``timestamp`` is the source time in seconds; without it each call advances
        the clock by one ``target_fps`` period. Frames arriving faster than the
        target rate return the previous result.
        """
        fps = target_fps or self.target_fps
        if timestamp is None:
            self._clock += 1.0 / fps
            timestamp = self._clock
        if (
            self._last_t is not None
            and self._last_result is not None
            and timestamp - self._last_t < 1.0 / fps - 1e-3
        ):
            # A repeated frame must not re-emit the fall event.
            return replace(self._last_result, fall_event=None)
        self._last_t = timestamp

        result = self._infer(frame, model, timestamp)
        self._last_result = result
        return result

    def _infer(
        self, frame: np.ndarray, model: Any | None, timestamp: float
    ) -> FrameInferenceResult:
        h, w = frame.shape[:2]
        if model is None or self._pipeline is None:
            return _idle_result()
        try:
            res = model.track(
                frame, persist=True, tracker="bytetrack.yaml", conf=0.25, imgsz=640, verbose=False
            )[0]
            pose_frame = adapt_pose_results(res)
            ids = (
                [int(t) for t in res.boxes.id.tolist()]
                if res.boxes is not None and res.boxes.id is not None
                else []
            )
            people = [
                (tid, p) for tid, p in zip(ids, pose_frame.persons, strict=False) if tid is not None
            ]
            if not people:
                return _idle_result()
            stable = self._stitcher.update(timestamp, [(t, p.bbox_xyxy) for t, p in people])

            best: tuple[tuple[int, float], FrameInferenceResult] | None = None
            for track_id, (_, person) in zip(stable, people, strict=True):
                obs = TrackObservation(
                    camera_id="live",
                    track_id=track_id,
                    timestamp=timestamp,
                    bbox_xyxy=person.bbox_xyxy,
                    detection_confidence=person.detection_confidence,
                    keypoints=person.keypoints,
                    image_width=w,
                    image_height=h,
                )
                sig = self._pipeline.compute_signals(obs, keep_features=False)
                fall_state, event = self._pipeline.decision.step(sig)
                pp = self._pipeline.decision.get_post_processor("live", track_id)
                if event is not None:
                    self._alerted.add(track_id)
                elif track_id in self._alerted and not pp.is_in_alerted_episode:
                    self._alerted.discard(track_id)

                if track_id in self._alerted:
                    label, rank = "FALL_DETECTED", 3
                    conf = max(sig.p_fallen, sig.p_falling)
                elif _STATE_RANK.get(fall_state, 0) > 0:
                    label, rank = "FALLING", _STATE_RANK[fall_state]
                    conf = max(sig.p_falling, sig.p_fallen)
                else:
                    label, rank = "NORMAL", 0
                    conf = 1.0 - max(sig.p_falling, sig.p_fallen)

                x1, y1, x2, y2 = (int(v) for v in person.bbox_xyxy)
                hip_y = _hip_y(person)
                prev = self._prev_hip_y.get(track_id)
                vy = (hip_y - prev) * self.target_fps / float(h) if prev is not None else 0.0
                self._prev_hip_y[track_id] = hip_y
                kpts = np.array(
                    [
                        [k.x, k.y, k.confidence] if k.present else [0.0, 0.0, 0.0]
                        for k in person.keypoints
                    ],
                    dtype=np.float32,
                )
                out = FrameInferenceResult(
                    state=label,
                    confidence=float(conf),
                    vertical_velocity=float(vy),
                    aspect_ratio=max(1, x2 - x1) / float(max(1, y2 - y1)),
                    floor_proximity=min(1.0, hip_y / float(h)),
                    keypoints=kpts,
                    bbox=(x1, y1, x2, y2),
                    track_id=track_id,
                    fall_event=event,
                )
                key = (rank, (x2 - x1) * (y2 - y1))
                if best is None or key > best[0]:
                    best = (key, out)
            return best[1] if best is not None else _idle_result()
        except Exception as e:  # noqa: BLE001 - keep the demo running
            LOG.warning("Inference error: %s", e)
            return _idle_result()


def _hip_y(person: Any) -> float:
    hips = [k.y for k in person.keypoints[11:13] if k.present and k.y is not None]
    if hips:
        return float(sum(hips) / len(hips))
    return float((person.bbox_xyxy[1] + person.bbox_xyxy[3]) / 2.0)


def _idle_result() -> FrameInferenceResult:
    """No person (or no model): nothing to report."""
    return FrameInferenceResult(
        state="NORMAL",
        confidence=0.0,
        vertical_velocity=0.0,
        aspect_ratio=0.0,
        floor_proximity=0.0,
        keypoints=None,
        bbox=None,
        track_id=-1,
    )
