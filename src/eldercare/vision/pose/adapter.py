"""Pose-result adapter: Ultralytics ``Results`` → stable internal contract (P2-003).

Representation contract (contract-first; downstream reads this, not ``Results``):

- PIXEL space + image dims: ``PersonPose.bbox_xyxy`` and present keypoint
  ``(x, y)`` are original-image PIXEL coordinates; ``PoseFrame`` always carries
  ``image_width``/``image_height`` so downstream can normalize for
  distance-invariance itself (AI_SPEC §6). The normalized ``xyn`` variant is
  deliberately NOT stored (single source of truth, no dual-representation drift).
- Missingness rule: a keypoint is missing ⟺ its source x or y is non-finite
  (NaN/±Inf) ⟺ stored as ``(None, None, conf, present=False)``. NEVER
  fabricated: no zeros-for-missing, no interpolation.
- No-threshold policy: ALL confidences (per-keypoint and detection) are
  preserved verbatim — even for missing keypoints, even when low. Confidence
  filtering/policy belongs downstream (track observation / temporal engine).
  The only confidence defect is a non-measurement: NaN/±Inf confidence is
  fail-closed ``ValueError`` (a bit-for-bit preservation test can only use
  real values — NaN never equals itself).
- Zero-person contract: ``keypoints is None`` (Ultralytics no-detection shape)
  → ``persons == ()``; image dims are still required and returned.

Duck-typed input surface (no ultralytics/torch/cv2 import here or in tests)::

    results.keypoints.xy    (N, 17, 2) pixel coords (torch Tensor / ndarray / lists)
    results.keypoints.conf  (N, 17)    per-keypoint confidences (same container kinds)
    results.boxes.xyxy      (N, 4)     pixel boxes (same container kinds)
    results.boxes.conf      (N,)       detection confidences in [0, 1]
    results.orig_shape      (h, w)     image size, positive ints (required always)

Containers are read via ``.tolist()`` when available, otherwise used as
sequences — so torch tensors, numpy arrays, and nested lists all work without
importing their frameworks.

P2-004 handoff: live ``Results`` from ``yolo26s-pose.pt`` enter the pipeline
EXCLUSIVELY through :func:`adapt_pose_results`. ARCHITECTURE §5 track
observation mapping: ``keypoints[17]`` ← ``person.keypoints[i].(x, y)``
(``None`` = missing, never fabricated), ``keypoint_confidence[17]`` ←
``person.keypoints[i].confidence`` verbatim, ``bbox`` ← ``bbox_xyxy``.

Fail-closed: every structural defect below raises ``ValueError`` naming the
defect (never a fabricated pose, never a silent default).
"""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from typing import Any

KEYPOINT_NAMES: tuple[str, ...] = (
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
"""COCO-ordered keypoint names (AI_SPEC §4); index-aligned with keypoint tuples."""

KEYPOINT_COUNT = 17
"""Expected keypoints per person (P2-002 measured ``(N, 17, 2)`` / ``(N, 17)``)."""

_MISSING: Any = object()


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
    """Return nested plain-Python data via ``.tolist()`` when available.

    torch Tensors and numpy arrays expose ``.tolist()``; nested lists/tuples
    pass through unchanged. No framework import required.
    """
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return value


def _parse_image_dims(orig_shape: Any) -> tuple[int, int]:
    """Parse ``results.orig_shape`` (h, w) into ``(width, height)`` positive ints."""
    if orig_shape is None:
        raise ValueError("invalid image dims: results.orig_shape is None")
    try:
        height_raw, width_raw = orig_shape
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid image dims: results.orig_shape must be (height, width), got {orig_shape!r}"
        ) from exc
    try:
        height, width = operator.index(height_raw), operator.index(width_raw)
    except TypeError as exc:
        raise ValueError(
            f"invalid image dims: results.orig_shape must hold ints, got {orig_shape!r}"
        ) from exc
    if height <= 0 or width <= 0:
        raise ValueError(
            f"invalid image dims: results.orig_shape must be positive, got {orig_shape!r}"
        )
    return width, height


@dataclass(frozen=True)
class Keypoint:
    """One index-aligned keypoint: pixel coords (or missing) + raw confidence.

    Invariant: ``present ⟺ (x is not None and y is not None)``. Confidence is
    ALWAYS preserved verbatim, even when ``present`` is False — but it must be
    a real (finite) measurement: NaN/±Inf confidence is fail-closed
    ``ValueError``. No range check here (no thresholding; policy is downstream).
    """

    x: float | None
    y: float | None
    confidence: float
    present: bool

    def __post_init__(self) -> None:
        x = self.x if self.x is None else _as_float(self.x, what="Keypoint.x")
        y = self.y if self.y is None else _as_float(self.y, what="Keypoint.y")
        confidence = _as_float(self.confidence, what="Keypoint.confidence")
        if not math.isfinite(confidence):
            raise ValueError(
                f"Keypoint.confidence must be a finite measurement, got {self.confidence!r}"
            )
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "confidence", confidence)
        if not isinstance(self.present, bool):
            raise ValueError(
                f"Keypoint.present must be bool, got {self.present!r} "
                "(invariant: present ⟺ (x is not None and y is not None))"
            )
        if (x is None) != (y is None):
            raise ValueError(
                "Keypoint coords must be both set or both None "
                f"(invariant: present ⟺ both present), got x={x!r}, y={y!r}, "
                f"present={self.present!r}"
            )
        if self.present != (x is not None and y is not None):
            raise ValueError(
                "Keypoint invariant violated: present ⟺ "
                f"(x is not None and y is not None), got x={x!r}, y={y!r}, "
                f"present={self.present!r}"
            )


@dataclass(frozen=True)
class PersonPose:
    """One detected person's pose: pixel bbox + detection conf + 17 keypoints."""

    bbox_xyxy: tuple[float, float, float, float]
    detection_confidence: float
    keypoints: tuple[Keypoint, ...]

    def __post_init__(self) -> None:
        bbox = tuple(self.bbox_xyxy) if isinstance(self.bbox_xyxy, list) else self.bbox_xyxy
        if len(bbox) != 4:
            raise ValueError(
                f"PersonPose bbox_xyxy must hold 4 pixel coords, got {self.bbox_xyxy!r}"
            )
        coords = tuple(_as_float(v, what="PersonPose.bbox_xyxy") for v in bbox)
        if any(not math.isfinite(v) for v in coords):
            raise ValueError(f"PersonPose bbox_xyxy must be finite pixel coords, got {coords!r}")
        x1, y1, x2, y2 = coords
        if not (x1 <= x2 and y1 <= y2):
            raise ValueError(
                "PersonPose bbox_xyxy ordering violated (need x1 <= x2 and y1 <= y2), "
                f"got {coords!r}"
            )
        object.__setattr__(self, "bbox_xyxy", coords)
        confidence = _as_float(self.detection_confidence, what="detection confidence")
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "PersonPose detection confidence must be finite in [0, 1], "
                f"got {self.detection_confidence!r}"
            )
        object.__setattr__(self, "detection_confidence", confidence)
        keypoints = tuple(self.keypoints) if isinstance(self.keypoints, list) else self.keypoints
        if len(keypoints) != KEYPOINT_COUNT:
            raise ValueError(
                "PersonPose keypoints must hold exactly "
                f"{KEYPOINT_COUNT} entries, got {len(keypoints)}"
            )
        for kp in keypoints:
            if not isinstance(kp, Keypoint):
                raise TypeError(f"PersonPose keypoints must all be Keypoint, got {kp!r}")
        object.__setattr__(self, "keypoints", keypoints)


@dataclass(frozen=True)
class PoseFrame:
    """One frame's normalized pose output; ``persons == ()`` = no detections."""

    image_width: int
    image_height: int
    persons: tuple[PersonPose, ...]

    def __post_init__(self) -> None:
        try:
            width, height = operator.index(self.image_width), operator.index(self.image_height)
        except TypeError as exc:
            raise ValueError(
                "PoseFrame image dims must be ints, got "
                f"width={self.image_width!r}, height={self.image_height!r}"
            ) from exc
        if width <= 0 or height <= 0:
            raise ValueError(
                f"PoseFrame image dims must be positive, got width={width!r}, height={height!r}"
            )
        object.__setattr__(self, "image_width", width)
        object.__setattr__(self, "image_height", height)
        persons = tuple(self.persons) if isinstance(self.persons, list) else self.persons
        for person in persons:
            if not isinstance(person, PersonPose):
                raise TypeError(f"PoseFrame persons must all be PersonPose, got {person!r}")
        object.__setattr__(self, "persons", persons)


def _as_rows(value: Any, *, what: str) -> list[Any]:
    """Materialize a per-person nested container as a list of rows."""
    rows = _materialize(value)
    if isinstance(rows, (str, bytes)) or not isinstance(rows, (list, tuple)):
        raise ValueError(f"{what} must be a nested sequence, got {value!r}")
    return list(rows)


def _as_confidence_list(value: Any, *, what: str, expected: int) -> list[float]:
    """Materialize a flat per-person confidence container, un-nesting (N, 1)."""
    flat: list[float] = []
    for item in _as_rows(value, what=what):
        if isinstance(item, (list, tuple)):
            if len(item) != 1:
                raise ValueError(
                    f"{what} person-count mismatch: expected {expected} scalar confidences"
                )
            item = item[0]
        flat.append(_as_float(item, what=what))
    if len(flat) != expected:
        raise ValueError(f"{what} person-count mismatch: expected {expected}, got {len(flat)}")
    return flat


def adapt_pose_results(results: Any) -> PoseFrame:
    """Normalize duck-typed Ultralytics pose ``Results`` into a :class:`PoseFrame`.

    Reads ONLY ``results.keypoints`` (``.xy``/``.conf``), ``results.boxes``
    (``.xyxy``/``.conf``), and ``results.orig_shape`` (h, w).

    Raises:
        ValueError: on ``results=None``; missing/malformed ``orig_shape``;
            keypoint dim ≠ 17; xy/conf length mismatch; non-finite keypoint
            confidence; boxes/person count mismatch; non-finite or
            out-of-range detection confidence; invalid bbox ordering;
            non-finite bbox coords.
    """
    if results is None:
        raise ValueError("results is None: refusing to fabricate a pose frame")
    width, height = _parse_image_dims(getattr(results, "orig_shape", None))

    keypoints = getattr(results, "keypoints", _MISSING)
    if keypoints is _MISSING:
        raise ValueError("results.keypoints attribute is missing")
    if keypoints is None:
        return PoseFrame(image_width=width, image_height=height, persons=())

    xy = getattr(keypoints, "xy", _MISSING)
    if xy is _MISSING:
        raise ValueError("results.keypoints.xy attribute is missing")
    conf = getattr(keypoints, "conf", _MISSING)
    if conf is _MISSING or conf is None:
        raise ValueError(
            "results.keypoints.conf is missing: per-keypoint confidences must be "
            "preserved, never defaulted"
        )
    xy_rows = _as_rows(xy, what="results.keypoints.xy")
    conf_rows = _as_rows(conf, what="results.keypoints.conf")
    if len(xy_rows) != len(conf_rows):
        raise ValueError(
            "keypoint xy/conf person-count mismatch: "
            f"{len(xy_rows)} xy rows vs {len(conf_rows)} conf rows"
        )
    persons_count = len(xy_rows)

    boxes = getattr(results, "boxes", _MISSING)
    if boxes is _MISSING or boxes is None:
        if persons_count == 0:
            return PoseFrame(image_width=width, image_height=height, persons=())
        raise ValueError(
            "boxes/person count mismatch: results.boxes is missing for "
            f"{persons_count} poses (refusing to guess the pairing)"
        )
    boxes_xyxy = getattr(boxes, "xyxy", _MISSING)
    if boxes_xyxy is _MISSING:
        raise ValueError("results.boxes.xyxy attribute is missing")
    boxes_conf_raw = getattr(boxes, "conf", _MISSING)
    if boxes_conf_raw is _MISSING or boxes_conf_raw is None:
        raise ValueError("results.boxes.conf is missing")
    box_rows = _as_rows(boxes_xyxy, what="results.boxes.xyxy")
    box_conf = _as_confidence_list(
        boxes_conf_raw,
        what="results.boxes.conf",
        expected=persons_count,
    )
    if len(box_rows) != persons_count:
        raise ValueError(
            "boxes/person count mismatch: "
            f"{len(box_rows)} boxes vs {persons_count} poses "
            "(refusing to guess the pairing)"
        )

    persons: list[PersonPose] = []
    for i in range(persons_count):
        xy_row = xy_rows[i]
        conf_row = conf_rows[i]
        if not isinstance(xy_row, (list, tuple)) or len(xy_row) != KEYPOINT_COUNT:
            got = len(xy_row) if isinstance(xy_row, (list, tuple)) else type(xy_row)
            raise ValueError(
                f"person {i}: expected {KEYPOINT_COUNT} keypoints in "
                f"results.keypoints.xy, got {got!r}"
            )
        if not isinstance(conf_row, (list, tuple)) or len(conf_row) != KEYPOINT_COUNT:
            got = len(conf_row) if isinstance(conf_row, (list, tuple)) else type(conf_row)
            raise ValueError(
                f"person {i}: expected {KEYPOINT_COUNT} confidences in "
                f"results.keypoints.conf, got {got!r}"
            )
        adapted: list[Keypoint] = []
        for k in range(KEYPOINT_COUNT):
            pair = xy_row[k]
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"person {i} keypoint {k}: expected an (x, y) pair, got {pair!r}")
            x = _as_float(pair[0], what=f"person {i} keypoint {k} x")
            y = _as_float(pair[1], what=f"person {i} keypoint {k} y")
            confidence = _as_float(conf_row[k], what=f"person {i} keypoint {k} confidence")
            if not math.isfinite(x) or not math.isfinite(y):
                adapted.append(Keypoint(x=None, y=None, confidence=confidence, present=False))
            else:
                adapted.append(Keypoint(x=x, y=y, confidence=confidence, present=True))
        box = box_rows[i]
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError(
                f"person {i}: expected 4 bbox coords in results.boxes.xyxy, got {box!r}"
            )
        persons.append(
            PersonPose(
                bbox_xyxy=(
                    _as_float(box[0], what=f"person {i} bbox x1"),
                    _as_float(box[1], what=f"person {i} bbox y1"),
                    _as_float(box[2], what=f"person {i} bbox x2"),
                    _as_float(box[3], what=f"person {i} bbox y2"),
                ),
                detection_confidence=box_conf[i],
                keypoints=tuple(adapted),
            )
        )
    return PoseFrame(image_width=width, image_height=height, persons=tuple(persons))
