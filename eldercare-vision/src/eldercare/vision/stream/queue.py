"""Bounded latest-frame queue for the RTSP pipeline (P1-003).

Freshness over completeness: when the consumer falls behind, stale frames
are discarded deterministically so the newest frame is always available.
Never unbounded, never blocking.

Default ``maxsize=2`` per pack ``ARCHITECTURE.md`` §4 (bounded queue
size 1–2 between the RTSP decoder and the inference worker).
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Generic, TypeVar

_T = TypeVar("_T")


class LatestFrameQueue(Generic[_T]):
    """Thread-safe bounded queue keeping the newest frames.

    Retention: the buffer always holds the LAST ``maxsize`` frames in
    arrival order; :meth:`get` yields the oldest retained frame first
    (FIFO among retained).

    Topology: safe for one producer + one consumer; more producers (or
    consumers) remain correct via the same lock.

    Close semantics: :meth:`close` is idempotent and sets a closed flag.
    After close, :meth:`put` raises ``RuntimeError("queue is closed")``
    (fail-fast) while :meth:`get` keeps draining retained frames and
    returns ``None`` once empty.

    Counters (``submitted``/``dropped``) are monotonic: they only ever
    increase, including across :meth:`clear` and :meth:`close`, so a later
    telemetry task can derive rates from them.
    """

    def __init__(self, maxsize: int = 2) -> None:
        """Create the queue with capacity ``maxsize`` (must be >= 1)."""
        if maxsize < 1:
            raise ValueError(f"maxsize must be >= 1, got {maxsize!r}")
        self._maxsize: int = maxsize
        self._buffer: deque[_T] = deque()
        self._lock = threading.Lock()
        self._submitted: int = 0
        self._dropped: int = 0
        self._closed: bool = False

    @property
    def maxsize(self) -> int:
        """Configured capacity (fixed at construction)."""
        return self._maxsize

    @property
    def submitted(self) -> int:
        """Total accepted puts (including puts that caused a drop)."""
        with self._lock:
            return self._submitted

    @property
    def dropped(self) -> int:
        """Total discarded stale frames."""
        with self._lock:
            return self._dropped

    @property
    def depth(self) -> int:
        """Current buffer size; ``0 <= depth <= maxsize`` always holds."""
        with self._lock:
            return len(self._buffer)

    @property
    def closed(self) -> bool:
        """Whether :meth:`close` has been called."""
        with self._lock:
            return self._closed

    def put(self, frame: _T) -> bool:
        """Store ``frame`` without blocking; return whether a stale frame was dropped.

        Never waits and never raises for a full queue: if the buffer is
        full, the OLDEST frame is discarded (``dropped += 1``) and the
        newest is stored. Returns ``True`` when a drop occurred, else
        ``False``.

        Raises:
            RuntimeError: if the queue is closed (fail-fast).
        """
        # Invariant: no I/O, no logging, no user callbacks inside the
        # critical section — bulk/mutation work stays minimal under the lock.
        with self._lock:
            if self._closed:
                raise RuntimeError("queue is closed")
            dropped = len(self._buffer) >= self._maxsize
            if dropped:
                self._buffer.popleft()
                self._dropped += 1
            self._buffer.append(frame)
            self._submitted += 1
            return dropped

    def get(self) -> _T | None:
        """Pop the OLDEST retained frame; ``None`` when empty (incl. after close).

        Never blocks and never raises for an empty queue.
        """
        # Invariant: no I/O, no logging, no user callbacks inside the
        # critical section — see put().
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer.popleft()

    def clear(self) -> None:
        """Empty the buffer; counters stay monotonic (not reset)."""
        with self._lock:
            self._buffer.clear()

    def close(self) -> None:
        """Mark the queue closed; idempotent (safe to call xN)."""
        with self._lock:
            self._closed = True

    def __repr__(self) -> str:
        # Payload-free by design: frames may hold images, so only
        # scalar state is rendered.
        with self._lock:
            return (
                f"LatestFrameQueue(maxsize={self._maxsize!r}, "
                f"depth={len(self._buffer)!r}, "
                f"submitted={self._submitted!r}, "
                f"dropped={self._dropped!r}, "
                f"closed={self._closed!r})"
            )

    def __str__(self) -> str:
        return self.__repr__()


__all__ = ["LatestFrameQueue"]
