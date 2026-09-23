"""Derived keypoint cache schema and provenance tracking (P4-006).

Per DATASET_PLAN.md §9 and AI_SPEC.md:
Derived keypoints are cached for accelerated development, threshold calibration,
and offline sequence evaluation. All cached sequences MUST carry complete provenance
metadata (model name, library version, inference config, extraction timestamp, sample ID)
and MUST be explicitly tagged as derived (is_derived=True, is_ground_truth=False)
to prevent pseudo-keypoint leakage into ground-truth datasets.
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass, field
from typing import Any

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint


def _as_float(value: Any, *, what: str) -> float:
    """Convert scalar to float with naming ValueError on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a real number, got bool {value!r}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be a real number, got {value!r}") from exc
    return result


def _check_non_empty_str(value: Any, *, what: str) -> str:
    """Validate that a value is a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be a non-empty string, got {value!r}")
    return value.strip()


def _check_bbox(value: Any) -> tuple[float, float, float, float]:
    """Validate a bounding box (4 finite ordered floats: x1 <= x2, y1 <= y2)."""
    coords = tuple(value) if isinstance(value, (list, tuple)) else None
    if coords is None or len(coords) != 4:
        raise ValueError(f"bbox must hold exactly 4 coordinates, got {value!r}")
    parsed = tuple(_as_float(v, what="bbox coordinate") for v in coords)
    if any(not math.isfinite(v) for v in parsed):
        raise ValueError(f"bbox coordinates must be finite, got {parsed!r}")
    x1, y1, x2, y2 = parsed
    if not (x1 <= x2 and y1 <= y2):
        raise ValueError(f"bbox ordering violated (x1<=x2, y1<=y2 required), got {parsed!r}")
    return parsed  # type: ignore[return-value]


def _check_keypoints(value: Any) -> tuple[Keypoint, ...]:
    """Validate tuple of exactly 17 Keypoint value objects."""
    kps = tuple(value) if isinstance(value, (list, tuple)) else None
    if kps is None or len(kps) != KEYPOINT_COUNT:
        raise ValueError(f"keypoints must hold exactly {KEYPOINT_COUNT} entries, got {value!r}")
    for idx, kp in enumerate(kps):
        if not isinstance(kp, Keypoint):
            raise TypeError(f"keypoint {idx} must be a Keypoint instance, got {kp!r}")
    return kps


@dataclass(frozen=True)
class KeypointCacheMetadata:
    """Traceable provenance metadata for derived keypoint sequence files."""

    source_sample_id: str
    model_name: str
    inference_library_version: str
    extraction_timestamp: str
    total_frames: int
    inference_config: dict[str, Any] = field(default_factory=dict)
    source_checksum: str | None = None
    fps: float | None = None
    schema_version: str = "1.0"
    is_derived: bool = True
    is_ground_truth: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_sample_id",
            _check_non_empty_str(self.source_sample_id, what="source_sample_id"),
        )
        object.__setattr__(
            self,
            "model_name",
            _check_non_empty_str(self.model_name, what="model_name"),
        )
        object.__setattr__(
            self,
            "inference_library_version",
            _check_non_empty_str(self.inference_library_version, what="inference_library_version"),
        )
        object.__setattr__(
            self,
            "extraction_timestamp",
            _check_non_empty_str(self.extraction_timestamp, what="extraction_timestamp"),
        )
        object.__setattr__(
            self,
            "schema_version",
            _check_non_empty_str(self.schema_version, what="schema_version"),
        )

        if (
            isinstance(self.total_frames, bool)
            or not isinstance(self.total_frames, int)
            or self.total_frames < 0
        ):
            raise ValueError(f"total_frames must be a non-negative int, got {self.total_frames!r}")

        if not isinstance(self.inference_config, dict):
            raise TypeError(
                f"inference_config must be a dict, got {type(self.inference_config).__name__}"
            )

        if self.source_checksum is not None:
            if not isinstance(self.source_checksum, str) or not self.source_checksum.strip():
                raise ValueError(
                    "source_checksum must be a non-empty string or None, "
                    f"got {self.source_checksum!r}"
                )
            object.__setattr__(self, "source_checksum", self.source_checksum.strip())

        if self.fps is not None:
            fps_val = _as_float(self.fps, what="fps")
            if fps_val <= 0 or not math.isfinite(fps_val):
                raise ValueError(f"fps must be a positive finite float, got {self.fps!r}")
            object.__setattr__(self, "fps", fps_val)

        if not isinstance(self.is_derived, bool) or not self.is_derived:
            raise ValueError("is_derived must be True for cached derived keypoints")

        if not isinstance(self.is_ground_truth, bool) or self.is_ground_truth:
            raise ValueError(
                "is_ground_truth must be False (pseudo-keypoints cannot be marked as ground truth)"
            )


@dataclass(frozen=True)
class CachedPerson:
    """One person detection within a cached frame."""

    track_id: int | None
    bbox_xyxy: tuple[float, float, float, float]
    detection_confidence: float
    keypoints: tuple[Keypoint, ...]

    def __post_init__(self) -> None:
        if self.track_id is not None:
            if (
                isinstance(self.track_id, bool)
                or not isinstance(self.track_id, int)
                or self.track_id < 0
            ):
                raise ValueError(
                    f"track_id must be a non-negative int or None, got {self.track_id!r}"
                )

        object.__setattr__(self, "bbox_xyxy", _check_bbox(self.bbox_xyxy))

        conf = _as_float(self.detection_confidence, what="detection_confidence")
        if not math.isfinite(conf) or not 0.0 <= conf <= 1.0:
            raise ValueError(f"detection_confidence must be in [0, 1], got {conf!r}")
        object.__setattr__(self, "detection_confidence", conf)

        object.__setattr__(self, "keypoints", _check_keypoints(self.keypoints))


@dataclass(frozen=True)
class CachedFrame:
    """One frame of derived person detections in a sequence."""

    frame_index: int
    timestamp: float
    image_width: int
    image_height: int
    persons: tuple[CachedPerson, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            isinstance(self.frame_index, bool)
            or not isinstance(self.frame_index, int)
            or self.frame_index < 0
        ):
            raise ValueError(f"frame_index must be a non-negative int, got {self.frame_index!r}")

        ts = _as_float(self.timestamp, what="timestamp")
        if not math.isfinite(ts) or ts < 0.0:
            raise ValueError(f"timestamp must be a finite float >= 0, got {ts!r}")
        object.__setattr__(self, "timestamp", ts)

        try:
            w, h = operator.index(self.image_width), operator.index(self.image_height)
        except TypeError as exc:
            raise ValueError(
                f"image dimensions must be ints, got w={self.image_width!r}, "
                f"h={self.image_height!r}"
            ) from exc
        if (
            isinstance(self.image_width, bool)
            or isinstance(self.image_height, bool)
            or w <= 0
            or h <= 0
        ):
            raise ValueError(
                f"image dimensions must be positive ints, got w={self.image_width!r}, "
                f"h={self.image_height!r}"
            )
        object.__setattr__(self, "image_width", w)
        object.__setattr__(self, "image_height", h)

        raw_persons = tuple(self.persons) if isinstance(self.persons, (list, tuple)) else None
        if raw_persons is None:
            raise TypeError(f"persons must be a tuple of CachedPerson, got {self.persons!r}")
        for p in raw_persons:
            if not isinstance(p, CachedPerson):
                raise TypeError(f"persons elements must be CachedPerson instances, got {p!r}")
        object.__setattr__(self, "persons", raw_persons)


@dataclass(frozen=True)
class CachedKeypointSequence:
    """A complete sequence of cached keypoint frames with provenance metadata."""

    metadata: KeypointCacheMetadata
    frames: tuple[CachedFrame, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, KeypointCacheMetadata):
            raise TypeError(
                "metadata must be a KeypointCacheMetadata instance, "
                f"got {type(self.metadata).__name__}"
            )

        raw_frames = tuple(self.frames) if isinstance(self.frames, (list, tuple)) else None
        if raw_frames is None:
            raise TypeError(f"frames must be a sequence of CachedFrame, got {self.frames!r}")

        for idx, f in enumerate(raw_frames):
            if not isinstance(f, CachedFrame):
                raise TypeError(f"frame {idx} must be a CachedFrame instance, got {f!r}")

        # Ensure frame count matches metadata declaration
        if len(raw_frames) != self.metadata.total_frames:
            raise ValueError(
                "frame count mismatch: metadata specifies "
                f"total_frames={self.metadata.total_frames}, "
                f"but sequence contains {len(raw_frames)} frames"
            )

        object.__setattr__(self, "frames", raw_frames)
