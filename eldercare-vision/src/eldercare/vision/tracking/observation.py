"""TrackObservation domain contract: one tracked person at one time point (P3-002).

Contract-first: downstream temporal fall analysis consumes THIS type — never
Ultralytics ``Results``, never ByteTrack internals, never tracker objects.
Framework-independent: stdlib only at import time (no ultralytics/torch/cv2,
not even lazily — this module never touches the framework).

Field -> spec mapping (ARCHITECTURE §5 track observation):

- ``camera_id``: ``camera_id`` — caller-supplied (validated, never guessed).
- ``track_id``: ``track_id`` — ``TrackedPerson.track_id`` verbatim.
- ``timestamp``: ``timestamp`` — caller-supplied capture timestamp.
- ``bbox_xyxy``: ``bbox`` — ``PersonPose.bbox_xyxy`` verbatim.
- ``detection_confidence``: verbatim name — ``PersonPose`` value verbatim.
- ``keypoints``: ``keypoints[17]`` — ``PersonPose.keypoints`` verbatim.
- ``keypoints[i].confidence``: ``keypoint_confidence[17]`` — rides INSIDE
  ``keypoints`` (no parallel array: a second array would invite drift;
  single source of truth).
- ``image_width``/``image_height``: pixel-coordinate meaning — ``TrackedFrame``
  dims verbatim.

Deliberate omission 1 — ``pose_confidence_summary``: ARCHITECTURE §5 names it,
but no aggregation policy (mean/min/weighted) exists in any spec. Inventing one
here would bake an unjustified semantic into the domain contract. All 17 raw
confidences are preserved verbatim, so any summary remains computable
downstream — the temporal engine owns that policy.

Deliberate omission 2 — ``frame_id``: ARCHITECTURE §5 track observation carries
no frame identity; history is keyed by ``(camera_id, track_id)`` per AI_SPEC §5.
Inventing the field would invite sequence-number semantics this contract does
not own. Not added.

``track_id=None`` means the tracker established no ID for this person
(explicit, never defaulted-invisibly); ``None`` passes through the conversion
boundary unchanged.

``timestamp`` carries the source capture timestamp (seconds since an arbitrary
origin, ``>= 0``); the boundary does not define the clock — callers pass the
same capture-time value they would put on a ``PoseFrame``.

Immutability / shared-reference safety: ``TrackObservation`` is frozen, and the
keypoint tuples and ``PersonPose`` objects it derives from are immutable value
objects — the converter shares (not deep-copies) the per-person
``bbox``/``keypoints`` references. Sharing is safe because none of these
objects can be mutated in place.

No-retention: observations hold plain scalars/strings plus the reused Phase 2
``Keypoint`` value type. No framework objects, no images, no tracker state.

What is NOT here (later P3 tasks): per-track history buffers (P3-003),
expiry/cleanup (P3-004), temporal features, velocity, body angles, smoothing,
fall-state logic, thresholds, or filtering of any kind.
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from typing import Any

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint
from eldercare.vision.tracking.tracker import TrackedFrame


def _check_camera_id(value: Any) -> str:
    """Validate a camera identity (non-empty string; pattern lives upstream)."""
    if not isinstance(value, str):
        raise TypeError(f"camera_id must be a non-empty string, got {value!r}")
    if not value:
        raise ValueError(f"camera_id must be a non-empty string, got {value!r}")
    return value


def _check_track_id(value: Any) -> int | None:
    """Validate one observation track ID (``None`` or non-negative int, bools rejected)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"track_id must be an int or None, got bool {value!r}")
    if not isinstance(value, int):
        raise TypeError(f"track_id must be an int or None, got {value!r}")
    if value < 0:
        raise ValueError(f"track_id must be a non-negative int or None, got {value!r}")
    return value


def _check_timestamp(value: Any) -> float:
    """Validate a capture timestamp (finite float >= 0)."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"timestamp must be a finite float >= 0, got {value!r}")
    return float(value)


def _as_float(value: Any, *, what: str) -> float:
    """Convert a scalar to float, raising a naming ``ValueError`` on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a real number, got bool {value!r}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be a real number, got {value!r}") from exc
    return result


def _check_bbox(value: Any) -> tuple[float, float, float, float]:
    """Validate a pixel bbox (4 finite ordered coords, ``x1 <= x2``/``y1 <= y2``)."""
    bbox = tuple(value) if isinstance(value, list) else value
    if not isinstance(bbox, tuple) or len(bbox) != 4:
        raise ValueError(f"bbox_xyxy must hold 4 pixel coords, got {value!r}")
    coords = tuple(_as_float(v, what="bbox_xyxy") for v in bbox)
    if any(not math.isfinite(v) for v in coords):
        raise ValueError(f"bbox_xyxy must be finite pixel coords, got {coords!r}")
    x1, y1, x2, y2 = coords
    if not (x1 <= x2 and y1 <= y2):
        raise ValueError(
            f"bbox_xyxy ordering violated (need x1 <= x2 and y1 <= y2), got {coords!r}"
        )
    return coords


def _check_detection_confidence(value: Any) -> float:
    """Validate a detection confidence (finite, in ``[0, 1]``; no thresholding)."""
    confidence = _as_float(value, what="detection_confidence")
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError(f"detection_confidence must be finite in [0, 1], got {value!r}")
    return confidence


def _check_keypoints(value: Any) -> tuple[Keypoint, ...]:
    """Validate exactly 17 reused Phase 2 ``Keypoint`` entries."""
    keypoints = tuple(value) if isinstance(value, list) else value
    if not isinstance(keypoints, tuple):
        raise TypeError(
            f"keypoints must be a tuple of exactly {KEYPOINT_COUNT} Keypoint entries, got {value!r}"
        )
    if len(keypoints) != KEYPOINT_COUNT:
        raise ValueError(
            f"keypoints must hold exactly {KEYPOINT_COUNT} entries, got {len(keypoints)}"
        )
    for keypoint in keypoints:
        if not isinstance(keypoint, Keypoint):
            raise TypeError(f"keypoints must all be Keypoint, got {keypoint!r}")
    return keypoints


def _check_image_dims(width: Any, height: Any) -> tuple[int, int]:
    """Validate image dims (positive ints; bools rejected via ``operator.index``)."""
    try:
        parsed_width, parsed_height = operator.index(width), operator.index(height)
    except TypeError as exc:
        raise ValueError(
            f"image dims must be ints, got width={width!r}, height={height!r} (bools rejected)"
        ) from exc
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError(
            f"image dims must be ints, got width={width!r}, height={height!r} (bools rejected)"
        )
    if parsed_width <= 0 or parsed_height <= 0:
        raise ValueError(
            f"image dims must be positive, got width={parsed_width!r}, height={parsed_height!r}"
        )
    return parsed_width, parsed_height


@dataclass(frozen=True)
class TrackObservation:
    """One tracked person's observation at one frame/time point.

    Exact fields per ARCHITECTURE §5 (see module docstring for the mapping
    table and the two deliberate omissions). Per-keypoint confidences ride
    inside ``keypoints[i].confidence`` — there is intentionally no parallel
    ``keypoint_confidences`` array. Fail-closed: every field is validated;
    ``track_id=None`` is explicit (tracker established no ID).
    """

    camera_id: str
    track_id: int | None
    timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    detection_confidence: float
    keypoints: tuple[Keypoint, ...]
    image_width: int
    image_height: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _check_camera_id(self.camera_id))
        object.__setattr__(self, "track_id", _check_track_id(self.track_id))
        object.__setattr__(self, "timestamp", _check_timestamp(self.timestamp))
        object.__setattr__(self, "bbox_xyxy", _check_bbox(self.bbox_xyxy))
        object.__setattr__(
            self, "detection_confidence", _check_detection_confidence(self.detection_confidence)
        )
        object.__setattr__(self, "keypoints", _check_keypoints(self.keypoints))
        width, height = _check_image_dims(self.image_width, self.image_height)
        object.__setattr__(self, "image_width", width)
        object.__setattr__(self, "image_height", height)


def tracked_frame_to_observations(
    tracked: TrackedFrame, *, camera_id: str, timestamp: float
) -> tuple[TrackObservation, ...]:
    """Convert one :class:`TrackedFrame` into per-person observations (pure).

    Preserves input person ORDER (index order); one observation per input
    person (zero-person yields ``()``). Per-person ``bbox``,
    ``detection_confidence``, ``keypoints``, ``track_id``, and dims are copied
    verbatim — keypoint tuples and persons are immutable value objects, so
    shared references are safe and no deep copy is made. Deterministic:
    repeated calls on equal inputs yield equal outputs. ``track_id=None``
    passes through explicitly. ``camera_id``/``timestamp`` are validated like
    ``TrackObservation`` fields and applied to every output observation.
    """
    if not isinstance(tracked, TrackedFrame):
        raise TypeError(f"tracked must be a TrackedFrame, got {type(tracked).__name__}")
    checked_camera_id = _check_camera_id(camera_id)
    checked_timestamp = _check_timestamp(timestamp)
    return tuple(
        TrackObservation(
            camera_id=checked_camera_id,
            track_id=entry.track_id,
            timestamp=checked_timestamp,
            bbox_xyxy=entry.person.bbox_xyxy,
            detection_confidence=entry.person.detection_confidence,
            keypoints=entry.person.keypoints,
            image_width=tracked.image_width,
            image_height=tracked.image_height,
        )
        for entry in tracked.persons
    )
