"""Bounded per-track history keyed by tracked-person identity (P3-003).

Contract-first: downstream temporal fall analysis consumes per-track
``TrackObservation`` sequences from THIS store — never tracker internals.
Framework-independent: stdlib only at import time (``collections``,
``dataclasses``, ``typing``) plus reuse-by-import of ``TrackObservation``;
no ultralytics/torch/cv2, not even lazily.

Key rule: history is keyed by exactly ``(camera_id, track_id)`` per
AI_SPEC §5. ``track_id=None`` observations are IGNORED (no persistent
history is kept for unassigned tracks): the architecture requires history
keyed by track identity, and unassigned detections are routine (occlusion,
track birth/death), so raising would be hostile to the live loop. Ignoring
is explicit — documented here and covered by tests — never silent.

Append rule: first observation for a key is always accepted; later ones
require ``timestamp >= last`` and are APPENDED (duplicate timestamps are
legitimate same-frame re-observations; arrival order is preserved).
``timestamp < last`` fails closed with ``ValueError`` naming the key and
both stamps — historical evidence is never silently reordered or inserted
mid-stream, and the store is left unchanged. Timestamps compare per-key
only; cross-key order is independent.

Eviction: each key owns a ``deque`` with ``maxlen=max_observations``, so a
full buffer drops the OLDEST observation automatically and the newest is
always retained. Eviction is count-based only — time-based expiry is P3-004.

Bound semantics: storage is exactly one ``dict`` of ``maxlen`` deques, so
memory is bounded by ``(#keys) x max_observations`` and cannot grow with
stream length. No unbounded structure exists anywhere here (key material
lives only in the dict itself; reads build transient tuples).

Snapshot guarantees: ``snapshot`` returns a FRESH tuple, oldest → newest,
of the stored (immutable) observations — callers hold no deque, list, or
other reference into internal buffers and cannot mutate them. Unknown keys
yield ``()``, not an error.

Lifecycle: ``remove`` drops one key (``True`` iff a history existed;
unknown keys yield ``False``); ``clear`` drops everything; ``__len__`` is
the number of tracked keys. All deterministic.

Concurrency: single-owner by design, NO locks/threads. The pose pipeline
owns its per-frame state on one thread (see ``pipeline.py`` threading
note); the bounded frame queue remains the thread-safe handoff. Do not
share a ``TrackHistory`` across threads without external synchronization.

What is NOT here (later P3 tasks): time-based expiry/cleanup (P3-004),
temporal features, velocity, body angles, smoothing, fall scores/state
machines, thresholds, filtering of any kind.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from eldercare.vision.tracking.observation import TrackObservation

_DEFAULT_MAX_OBSERVATIONS = 60


def _check_max_observations(value: Any) -> int:
    """Validate the per-track capacity (positive int; bools rejected)."""
    if isinstance(value, bool):
        raise TypeError(f"max_observations must be a positive int, got bool {value!r}")
    if not isinstance(value, int):
        raise TypeError(f"max_observations must be a positive int, got {value!r}")
    if value <= 0:
        raise ValueError(f"max_observations must be a positive int, got {value!r}")
    return value


def _check_camera_key(value: Any) -> str:
    """Validate a history key camera identity (non-empty string)."""
    if not isinstance(value, str):
        raise TypeError(f"camera_id must be a non-empty string, got {value!r}")
    if not value:
        raise ValueError(f"camera_id must be a non-empty string, got {value!r}")
    return value


def _check_track_key(value: Any) -> int:
    """Validate a history key track identity (non-negative int, bools rejected)."""
    if value is None or isinstance(value, bool):
        raise TypeError(f"track_id must be a non-negative int, got {value!r}")
    if not isinstance(value, int):
        raise TypeError(f"track_id must be a non-negative int, got {value!r}")
    if value < 0:
        raise ValueError(f"track_id must be a non-negative int, got {value!r}")
    return value


@dataclass(frozen=True)
class TrackHistoryConfig:
    """Per-track history capacity (fixed maximum observations per key).

    Default ``max_observations=60`` is an ENGINEERING default (not a
    calibrated fall threshold), chosen against the AI_SPEC §9 bootstrap
    ``tracking.history_seconds: 2.0`` example: at typical fixed-camera
    rates of 15-30 fps, a 2 s window holds ~30-60 observations, so 60
    covers the full 2 s window at 30 fps (about 4 s at 15 fps) while
    staying a small constant per track. Eviction stays count-based only;
    time-based expiry is P3-004.
    """

    max_observations: int = _DEFAULT_MAX_OBSERVATIONS

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_observations", _check_max_observations(self.max_observations))


class TrackHistory:
    """Deterministic bounded store of per-track ``TrackObservation`` sequences."""

    def __init__(self, config: TrackHistoryConfig | None = None) -> None:
        """Create the store (default config when ``None``)."""
        if config is None:
            config = TrackHistoryConfig()
        if not isinstance(config, TrackHistoryConfig):
            raise TypeError(f"config must be a TrackHistoryConfig, got {type(config).__name__}")
        self._config = config
        self._buffers: dict[tuple[str, int], deque[TrackObservation]] = {}

    @property
    def config(self) -> TrackHistoryConfig:
        """Configured per-track capacity."""
        return self._config

    def append(self, obs: TrackObservation) -> None:
        """Append one observation to its ``(camera_id, track_id)`` history.

        ``track_id=None`` observations are ignored (see module docstring).
        Out-of-order timestamps fail closed with ``ValueError`` and leave
        the store unchanged.
        """
        if not isinstance(obs, TrackObservation):
            raise TypeError(f"obs must be a TrackObservation, got {type(obs).__name__}")
        track_id = obs.track_id
        if track_id is None:
            return
        key = (obs.camera_id, track_id)
        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = deque(maxlen=self._config.max_observations)
            self._buffers[key] = buffer
        if buffer:
            last = buffer[-1].timestamp
            if obs.timestamp < last:
                raise ValueError(
                    f"out-of-order timestamp for key {key!r}: "
                    f"got {obs.timestamp!r}, last is {last!r} "
                    "(history never reorders evidence)"
                )
        buffer.append(obs)

    def snapshot(self, camera_id: str, track_id: int) -> tuple[TrackObservation, ...]:
        """Return the key's history as a fresh tuple, oldest → newest (``()`` if unknown)."""
        key = (_check_camera_key(camera_id), _check_track_key(track_id))
        buffer = self._buffers.get(key)
        if buffer is None:
            return ()
        return tuple(buffer)

    def keys(self) -> tuple[tuple[str, int], ...]:
        """Return all tracked ``(camera_id, track_id)`` keys in first-seen order."""
        return tuple(self._buffers)

    def remove(self, camera_id: str, track_id: int) -> bool:
        """Drop one key's history (``True`` iff a history existed)."""
        key = (_check_camera_key(camera_id), _check_track_key(track_id))
        return self._buffers.pop(key, None) is not None

    def clear(self) -> None:
        """Drop every key's history."""
        self._buffers.clear()

    def __len__(self) -> int:
        """Number of tracked keys."""
        return len(self._buffers)

    def __repr__(self) -> str:
        # Scalar-only by design: observations carry confidences/keypoints,
        # so only counts and key identities are rendered.
        total = sum(len(buffer) for buffer in self._buffers.values())
        return (
            f"TrackHistory(max_observations={self._config.max_observations!r}, "
            f"tracks={len(self._buffers)!r}, "
            f"observations={total!r}, "
            f"keys={tuple(self._buffers)!r})"
        )


__all__ = ["TrackHistory", "TrackHistoryConfig"]
