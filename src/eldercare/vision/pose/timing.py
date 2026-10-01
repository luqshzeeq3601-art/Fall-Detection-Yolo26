"""Inference timing metrics for the pose pipeline (P2-005).

Units: MILLISECONDS everywhere (never seconds). What is measured — model
prediction time (``predict_ms``), pose-result adaptation time (``adapt_ms``),
and overall pipeline processing duration (``total_ms``) — ONLY. Capture
latency (frame acquisition) and queue waiting time are explicitly NOT
inference metrics and are never included: the pipeline stamps only around
``predictor.predict`` + ``adapt_pose_results``.

``None``-means-unmeasured rule: ``PosePipelineResult.timing`` is ``None``
only for hand-constructed results; every pipeline-produced success result
carries a real :class:`PoseTiming`. Read failures (``None`` paths) and
predictor/adapter failures produce no result and therefore no timing —
timings are never fabricated when a stage did not execute.

Anomaly policy: a backwards or non-finite timer stamp is a clock anomaly and
fails closed with a naming ``ValueError`` — never a negative duration, never
a clamped zero. The seconds-to-milliseconds scale-up can leave binary
representation dust (for example ``(100.010 - 100.0) * 1000.0`` evaluates to
``10.000000000005116``); each duration is normalized with ``round(..., 9)``,
which discards only sub-picosecond dust far below any clock resolution while
keeping controlled-stamp math exact. Ordering is checked on the raw stamps
BEFORE rounding, so a backwards clock is never rounded into hiding.

Later-telemetry handoff: CONSTRAINTS §11 ``inference latency`` is satisfied
by ``total_ms``; the per-stage breakdown rides on ``predict_ms`` /
``adapt_ms``. :meth:`PoseTiming.to_dict` exposes JSON-safe primitives only.

Stdlib ONLY: this module imports ``math`` + ``dataclasses`` and nothing else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_MS_PER_SECOND = 1000.0
_ROUND_NDIGITS = 9


def _check_milliseconds(value: object, name: str) -> float:
    """Validate one millisecond duration (finite ``float >= 0``; bools rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite float >= 0 (milliseconds), got {value!r}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite float >= 0 (milliseconds), got {value!r}")
    return result


def _check_stamp(value: object, name: str) -> float:
    """Validate one timer stamp (finite number; bools rejected, sign unchecked).

    No ``>= 0`` policy here: stamps are opaque clock readings whose origin is
    the timer's business. Only finiteness and ordering are enforced.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite timer stamp, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite timer stamp, got {value!r}")
    return result


@dataclass(frozen=True)
class PoseTiming:
    """Inference durations for one frame, all in MILLISECONDS.

    ``predict_ms`` covers ``predictor.predict`` only; ``adapt_ms`` covers
    ``adapt_pose_results`` only; ``total_ms`` covers predict + adapt.
    """

    predict_ms: float
    adapt_ms: float
    total_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "predict_ms", _check_milliseconds(self.predict_ms, "predict_ms"))
        object.__setattr__(self, "adapt_ms", _check_milliseconds(self.adapt_ms, "adapt_ms"))
        object.__setattr__(self, "total_ms", _check_milliseconds(self.total_ms, "total_ms"))

    def to_dict(self) -> dict[str, float]:
        """Return JSON-safe primitives (passes ``json.dumps(..., allow_nan=False)``)."""
        return {
            "predict_ms": self.predict_ms,
            "adapt_ms": self.adapt_ms,
            "total_ms": self.total_ms,
        }


def timings_from_stamps(t0: float, t1: float, t2: float) -> PoseTiming:
    """Build a :class:`PoseTiming` from three ordered timer stamps.

    Stamp ordering contract: ``t0`` = pre-predict, ``t1`` =
    post-predict/pre-adapt, ``t2`` = post-adapt. Durations are
    ``predict_ms = (t1 - t0) * 1000.0``, ``adapt_ms = (t2 - t1) * 1000.0``,
    ``total_ms = (t2 - t0) * 1000.0`` (milliseconds, never seconds).

    Raises:
        ValueError: naming the stamp on non-finite (or bool/non-numeric)
            stamps, or naming both stamps on backwards stamps (``t1 < t0``
            or ``t2 < t1``).
    """
    start = _check_stamp(t0, "t0")
    middle = _check_stamp(t1, "t1")
    end = _check_stamp(t2, "t2")
    if middle < start:
        raise ValueError(
            "clock anomaly: t1 < t0 "
            f"(t0={start!r}, t1={middle!r}): refusing to fabricate a negative duration"
        )
    if end < middle:
        raise ValueError(
            "clock anomaly: t2 < t1 "
            f"(t1={middle!r}, t2={end!r}): refusing to fabricate a negative duration"
        )
    return PoseTiming(
        predict_ms=round((middle - start) * _MS_PER_SECOND, _ROUND_NDIGITS),
        adapt_ms=round((end - middle) * _MS_PER_SECOND, _ROUND_NDIGITS),
        total_ms=round((end - start) * _MS_PER_SECOND, _ROUND_NDIGITS),
    )
