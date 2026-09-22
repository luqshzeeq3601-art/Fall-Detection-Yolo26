"""ByteTrack pose-tracking boundary: stable track IDs over Phase 2 poses (P3-001).

Contract-first: detected people receive stable track identities across
sequential frames while the Phase 2 normalized pose contract passes through
bit-for-bit (output persons ARE the input ``PersonPose`` objects: no
thresholding, no filtering, no reordering).

Backend surface (the seam fakes implement)::

    track(detections, image) -> tuple[int | None, ...]

one entry per input detection IN ORDER; ``None`` = the tracker established no
ID for that detection (never fabricated by this boundary).

Association rule (production backend only; pure tested helper
:func:`associate_detections_to_tracks`): detections are processed in input
order; each detection claims the highest-IoU still-unclaimed track box with
IoU strictly greater than 0.0 (ties resolve to the lowest track position);
claimed tracks are never reused within a frame. Detections with no overlapping
unclaimed track degrade to ``None``; surplus tracks are ignored. Count
mismatches therefore degrade per this rule — never silent misalignment.

Zero-person policy: ``PoseTracker.update`` still consults the backend with an
empty detection tuple (so ByteTrack session state ages honestly) and returns
an empty ``persons`` tuple.

``reset()`` contract: drops backend session state (production backend drops
its cached ``YOLO`` model so the next ``track`` starts a fresh session;
documented for camera-reconnect use). ``PoseTracker`` itself holds no
per-frame state (only config + backend); tracker-internal ByteTrack state is
owned by the backend.

What is NOT here (later P3 tasks): per-track history (P3-003), expiry/cleanup
(P3-004), the ``TrackObservation`` interface (P3-002), fall logic, thresholds.

Production-backend runtime assumptions (``torch``/``ultralytics`` are ABSENT
from this machine's venv and system Python — recorded, not installed):

- ``model.track(source=image, persist=..., tracker=..., verbose=False)``
  returns a one-element ``Results`` list per image (mirrors the
  ``predict(...)[0]`` precedent in ``pose/inference.py``); a bare ``Results``
  is accepted defensively.
- Track identities are read from ``Results.boxes.id`` with boxes from
  ``Results.boxes.xyxy``; ``boxes``/``boxes.id`` being ``None`` means the
  tracker established no IDs this frame (all detections degrade to ``None``).
- Only documented ``model.track`` kwargs are used: ``persist`` (official
  streaming kwarg) and ``tracker`` (stock ``bytetrack.yaml`` per CONSTRAINTS
  §2). No ``bytetrack.yaml`` tuning keys are guessed or set anywhere here.
- Live verification against real weights/GPU was NOT possible here; the
  production path is covered only by contract-shaped fakes, never executed.

Stdlib + numpy ONLY at module import time; ``ultralytics`` appears solely as
a LAZY import inside :meth:`UltralyticsByteTrackBackend.track`, mirroring
``pose/inference.py``.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from eldercare.vision.pose.adapter import PersonPose, PoseFrame

Bbox = tuple[float, float, float, float]

_DEFAULT_TRACKER = "bytetrack.yaml"
_DEFAULT_MODEL = "yolo26s-pose.pt"


def _check_tracker_name(value: Any) -> str:
    """Validate the tracker config file name (non-empty string)."""
    if not isinstance(value, str):
        raise TypeError(f"tracker must be a non-empty string, got {value!r}")
    if not value:
        raise ValueError(f"tracker must be a non-empty string, got {value!r}")
    return value


def _check_persist(value: Any) -> bool:
    """Validate the persist flag (real bool; numeric 0/1 rejected)."""
    if not isinstance(value, bool):
        raise TypeError(f"persist must be a bool, got {value!r}")
    return value


def _check_track_id(value: Any) -> int | None:
    """Validate one boundary track ID (``None`` or non-negative int, bools rejected)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"track_id must be an int or None, got bool {value!r}")
    if not isinstance(value, int):
        raise TypeError(f"track_id must be an int or None, got {value!r}")
    if value < 0:
        raise ValueError(f"track_id must be a non-negative int or None, got {value!r}")
    return value


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


def _check_image(value: Any) -> np.ndarray:
    """Validate a frame image (3-D HxWxC uint8 array; mirrors the pose pipeline)."""
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


def _as_float(value: Any, *, what: str) -> float:
    """Convert a scalar to float, raising a naming ``ValueError`` on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a real number, got bool {value!r}")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be a real number, got {value!r}") from exc
    return result


def _materialize(value: Any) -> Any:
    """Return nested plain-Python data via ``.tolist()`` when available."""
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return value


@dataclass(frozen=True)
class ByteTrackConfig:
    """ByteTrack selection: stock tracker config + streaming persistence flag.

    ``tracker`` defaults to ``"bytetrack.yaml"`` per CONSTRAINTS §2 (stock
    config only — no tuning keys exist on this type by design). ``persist``
    is the documented official ``model.track`` streaming kwarg (default
    ``True`` so track identities survive across sequential frames).
    """

    tracker: str = _DEFAULT_TRACKER
    persist: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracker", _check_tracker_name(self.tracker))
        object.__setattr__(self, "persist", _check_persist(self.persist))


class TrackBackend(Protocol):
    """Minimal tracking surface the boundary depends on.

    Fakes implement this method and return one entry per input detection IN
    ORDER; ``None`` = the tracker established no ID (the boundary never
    fabricates one). The production backend delegates to the real tracker.
    """

    def track(
        self,
        detections: tuple[Bbox, ...],
        image: np.ndarray,
    ) -> tuple[int | None, ...]:
        """Assign one track ID (or ``None``) per input detection, in order."""
        ...


def bbox_iou(first: Bbox, second: Bbox) -> float:
    """Intersection-over-union of two ``(x1, y1, x2, y2)`` pixel boxes.

    Degenerate (zero-area) boxes yield ``0.0`` — no overlap can be claimed
    with an empty box, and no division by zero is possible.
    """
    first_coords = tuple(_as_float(v, what="bbox_iou box") for v in first)
    second_coords = tuple(_as_float(v, what="bbox_iou box") for v in second)
    if len(first_coords) != 4 or len(second_coords) != 4:
        raise ValueError(f"bbox_iou boxes must each hold 4 coords, got {first!r} and {second!r}")
    x1 = max(first_coords[0], second_coords[0])
    y1 = max(first_coords[1], second_coords[1])
    x2 = min(first_coords[2], second_coords[2])
    y2 = min(first_coords[3], second_coords[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0.0:
        return 0.0
    first_area = max(0.0, first_coords[2] - first_coords[0]) * max(
        0.0, first_coords[3] - first_coords[1]
    )
    second_area = max(0.0, second_coords[2] - second_coords[0]) * max(
        0.0, second_coords[3] - second_coords[1]
    )
    union = first_area + second_area - inter
    if not math.isfinite(union) or union <= 0.0:
        return 0.0
    return inter / union


def associate_detections_to_tracks(
    detections: Sequence[Bbox],
    track_boxes: Sequence[Bbox],
    track_ids: Sequence[int],
) -> tuple[int | None, ...]:
    """Greedily associate detections to tracks by IoU (pure helper).

    Detections are processed in input order; each claims the highest-IoU
    still-unclaimed track box with IoU > 0.0 (ties resolve to the lowest
    track position). Claimed tracks are never reused within a frame.
    Unmatched detections yield ``None``; surplus tracks are ignored.
    """
    det_list = list(detections)
    box_list = list(track_boxes)
    id_list = list(track_ids)
    if len(box_list) != len(id_list):
        raise ValueError(
            "track boxes/ids count mismatch: "
            f"{len(box_list)} boxes vs {len(id_list)} ids (refusing to guess the pairing)"
        )
    claimed = [False] * len(box_list)
    assigned: list[int | None] = []
    for det_index, det in enumerate(det_list):
        best_pos: int | None = None
        best_iou = 0.0
        for pos, track_box in enumerate(box_list):
            if claimed[pos]:
                continue
            iou = bbox_iou(det, track_box)
            if iou > best_iou:
                best_iou = iou
                best_pos = pos
        if best_pos is None:
            assigned.append(None)
        else:
            claimed[best_pos] = True
            track_id = id_list[best_pos]
            if isinstance(track_id, bool) or not isinstance(track_id, int):
                raise TypeError(f"detection {det_index}: track id must be an int, got {track_id!r}")
            if track_id < 0:
                raise ValueError(
                    f"detection {det_index}: track id must be non-negative, got {track_id!r}"
                )
            assigned.append(track_id)
    return tuple(assigned)


@dataclass(frozen=True)
class TrackedPerson:
    """One Phase 2 person plus its tracker identity (``None`` = unassigned)."""

    person: PersonPose
    track_id: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.person, PersonPose):
            raise TypeError(f"person must be a PersonPose, got {type(self.person).__name__}")
        object.__setattr__(self, "track_id", _check_track_id(self.track_id))


@dataclass(frozen=True)
class TrackedFrame:
    """One frame's tracked output: image dims + identity-tagged persons."""

    image_width: int
    image_height: int
    persons: tuple[TrackedPerson, ...]

    def __post_init__(self) -> None:
        width, height = _check_image_dims(self.image_width, self.image_height)
        object.__setattr__(self, "image_width", width)
        object.__setattr__(self, "image_height", height)
        persons = tuple(self.persons) if isinstance(self.persons, list) else self.persons
        for person in persons:
            if not isinstance(person, TrackedPerson):
                raise TypeError(f"persons must all be TrackedPerson, got {type(person).__name__}")
        object.__setattr__(self, "persons", persons)


class UltralyticsByteTrackBackend:
    """Production :class:`TrackBackend` over ``YOLO(model_name)`` track mode.

    Args:
        model_name: Weights file (default ``"yolo26s-pose.pt"`` per
            CONSTRAINTS §2; resolved through the Ultralytics cache).
        config: Tracker selection (default stock ``bytetrack.yaml`` +
            ``persist=True``).

    The model loads once on first :meth:`track` via a LAZY
    ``from ultralytics import YOLO`` import (mirroring
    ``UltralyticsPosePredictor``); construction never touches the framework.
    No thresholding, no ID fabrication: whatever the tracker establishes is
    associated to the input detections by the documented greedy-IoU rule.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        config: ByteTrackConfig | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name:
            raise ValueError(f"model_name must be a non-empty string, got {model_name!r}")
        if config is None:
            config = ByteTrackConfig()
        if not isinstance(config, ByteTrackConfig):
            raise TypeError(f"config must be a ByteTrackConfig, got {type(config).__name__}")
        self._model_name = model_name
        self._config = config
        self._model: Any = None

    @property
    def model_name(self) -> str:
        """Configured weights file name."""
        return self._model_name

    @property
    def config(self) -> ByteTrackConfig:
        """Configured tracker selection."""
        return self._config

    def _check_detections(self, detections: Any) -> tuple[Bbox, ...]:
        """Validate the detection tuple (each row: 4 finite ordered numbers)."""
        if not isinstance(detections, (tuple, list)):
            raise TypeError(
                f"detections must be a tuple of bbox rows, got {type(detections).__name__}"
            )
        rows: list[Bbox] = []
        for index, row in enumerate(detections):
            if not isinstance(row, (tuple, list)) or len(row) != 4:
                raise ValueError(f"detection {index}: expected 4 bbox coords, got {row!r}")
            coords = tuple(_as_float(v, what=f"detection {index} bbox") for v in row)
            if any(not math.isfinite(v) for v in coords):
                raise ValueError(f"detection {index}: bbox coords must be finite, got {coords!r}")
            x1, y1, x2, y2 = coords
            if not (x1 <= x2 and y1 <= y2):
                raise ValueError(
                    "detection "
                    f"{index}: bbox ordering violated (need x1 <= x2 and y1 <= y2), "
                    f"got {coords!r}"
                )
            rows.append((x1, y1, x2, y2))
        return tuple(rows)

    def _normalize_track_id(self, value: Any, *, index: int) -> int:
        """Normalize one raw tracker ID (integral floats accepted, e.g. ``2.0``)."""
        if isinstance(value, bool):
            raise ValueError(f"track {index}: id must be an int, got bool {value!r}")
        if isinstance(value, int):
            track_id = value
        elif isinstance(value, float) and value.is_integer():
            track_id = int(value)
        else:
            raise ValueError(f"track {index}: id must be an int, got {value!r}")
        if track_id < 0:
            raise ValueError(f"track {index}: id must be non-negative, got {track_id!r}")
        return track_id

    def track(
        self,
        detections: tuple[Bbox, ...],
        image: np.ndarray,
    ) -> tuple[int | None, ...]:
        """Run ByteTrack on one image; associate established IDs to detections.

        Always calls ``model.track`` (even with zero detections) so tracker
        session state ages honestly. ``boxes``/``boxes.id`` being ``None``
        means the tracker established no IDs this frame — every detection
        degrades to ``None`` rather than a fabricated ID.

        Raises:
            ValueError: on malformed detections/image, an empty result list
                (fail closed — never fabricate tracks), track boxes/ids
                count mismatch, or non-int/negative track IDs.
        """
        from ultralytics import YOLO

        checked = self._check_detections(detections)
        _check_image(image)
        if self._model is None:
            self._model = YOLO(self._model_name)
        results = self._model.track(
            source=image,
            persist=self._config.persist,
            tracker=self._config.tracker,
            verbose=False,
        )
        if not results:
            raise ValueError(
                "Ultralytics tracker returned no results: refusing to fabricate tracks"
            )
        result = results[0] if isinstance(results, (list, tuple)) else results
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return (None,) * len(checked)
        raw_ids = getattr(boxes, "id", None)
        if raw_ids is None:
            return (None,) * len(checked)
        raw_boxes = getattr(boxes, "xyxy", None)
        if raw_boxes is None:
            raise ValueError("track result boxes lack xyxy: refusing to guess the pairing")
        id_rows = _materialize(raw_ids)
        box_rows = _materialize(raw_boxes)
        if not isinstance(id_rows, (list, tuple)) or not isinstance(box_rows, (list, tuple)):
            raise ValueError(
                "track result boxes/id must be sequences, "
                f"got id={type(id_rows).__name__}, boxes={type(box_rows).__name__}"
            )
        flat_ids: list[Any] = []
        for item in id_rows:
            if isinstance(item, (list, tuple)):
                if len(item) != 1:
                    raise ValueError(
                        f"track id/box count mismatch: nested id row is not scalar, got {item!r}"
                    )
                item = item[0]
            flat_ids.append(item)
        if len(flat_ids) != len(box_rows):
            raise ValueError(
                "track id/box count mismatch: "
                f"{len(flat_ids)} ids vs {len(box_rows)} boxes "
                "(refusing to guess the pairing)"
            )
        track_ids = [self._normalize_track_id(v, index=i) for i, v in enumerate(flat_ids)]
        track_boxes: list[Bbox] = []
        for index, row in enumerate(box_rows):
            if not isinstance(row, (list, tuple)) or len(row) != 4:
                raise ValueError(f"track {index}: expected 4 bbox coords, got {row!r}")
            coords = tuple(_as_float(v, what=f"track {index} bbox") for v in row)
            if any(not math.isfinite(v) for v in coords):
                raise ValueError(f"track {index}: bbox coords must be finite, got {coords!r}")
            x1, y1, x2, y2 = coords
            if not (x1 <= x2 and y1 <= y2):
                raise ValueError(f"track {index}: bbox ordering violated, got {coords!r}")
            track_boxes.append((x1, y1, x2, y2))
        return associate_detections_to_tracks(checked, tuple(track_boxes), tuple(track_ids))

    def reset(self) -> None:
        """Drop the cached model (and its ByteTrack session); camera-reconnect seam."""
        self._model = None

    def __repr__(self) -> str:
        return (
            f"UltralyticsByteTrackBackend(model_name={self._model_name!r}, config={self._config!r})"
        )


class PoseTracker:
    """Boundary assigning track IDs to normalized pose frames.

    Args:
        config: Tracker selection (default stock ``bytetrack.yaml`` +
            ``persist=True``).
        backend: ``TrackBackend`` implementation (default production
            :class:`UltralyticsByteTrackBackend`, built lazily — constructing
            a ``PoseTracker`` never imports ultralytics).

    Holds no per-frame state of its own (only config + backend references);
    ByteTrack session state is owned by the backend.
    """

    def __init__(
        self,
        config: ByteTrackConfig | None = None,
        backend: TrackBackend | None = None,
    ) -> None:
        if config is None:
            config = ByteTrackConfig()
        if not isinstance(config, ByteTrackConfig):
            raise TypeError(f"config must be a ByteTrackConfig, got {type(config).__name__}")
        if backend is None:
            backend = UltralyticsByteTrackBackend(config=config)
        if not callable(getattr(backend, "track", None)):
            raise TypeError(f"backend must expose a callable track method, got {backend!r}")
        self._config = config
        self._backend = backend

    @property
    def config(self) -> ByteTrackConfig:
        """Configured tracker selection."""
        return self._config

    @property
    def backend(self) -> TrackBackend:
        """Owned tracking backend (session state lives here, not on the boundary)."""
        return self._backend

    def update(self, pose: PoseFrame, image: np.ndarray) -> TrackedFrame:
        """Tag one :class:`PoseFrame` with track IDs.

        The backend is ALWAYS consulted (even with zero persons) so session
        state ages honestly. Output persons ARE the input ``PersonPose``
        objects (identity preserved, bit-exact, original order). Backend
        count mismatches and non-int/negative IDs fail closed; backend
        exceptions propagate unwrapped.
        """
        if not isinstance(pose, PoseFrame):
            raise TypeError(f"pose must be a PoseFrame, got {type(pose).__name__}")
        _check_image(image)
        detections = tuple(person.bbox_xyxy for person in pose.persons)
        track_ids = self._backend.track(detections, image)
        if not isinstance(track_ids, (tuple, list)):
            raise TypeError(
                f"backend must return a tuple of track IDs, got {type(track_ids).__name__}"
            )
        track_ids = tuple(track_ids)
        if len(track_ids) != len(pose.persons):
            raise ValueError(
                "backend/detection count mismatch: "
                f"{len(track_ids)} ids vs {len(pose.persons)} detections "
                "(refusing to guess the pairing)"
            )
        persons = tuple(
            TrackedPerson(person=person, track_id=_check_track_id(track_id))
            for person, track_id in zip(pose.persons, track_ids, strict=True)
        )
        return TrackedFrame(
            image_width=pose.image_width,
            image_height=pose.image_height,
            persons=persons,
        )

    def reset(self) -> None:
        """Drop backend session state (camera-reconnect seam; no-op past the call)."""
        reset = getattr(self._backend, "reset", None)
        if callable(reset):
            reset()

    def __repr__(self) -> str:
        return f"PoseTracker(config={self._config!r})"
