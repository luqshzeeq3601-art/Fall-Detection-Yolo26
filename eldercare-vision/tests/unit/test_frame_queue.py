"""Unit tests for LatestFrameQueue (P1-003).

TDD RED-first suite. Payload-agnostic: synthetic payloads (ints/strings/
objects) only — never real images. Threading stdlib only.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from eldercare.vision.stream.queue import LatestFrameQueue

# --- Basics -----------------------------------------------------------------


def test_empty_get_returns_none() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    assert q.get() is None
    assert q.depth == 0


def test_single_roundtrip() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    assert q.put("frame-a") is False  # no drop on empty queue
    assert q.depth == 1
    assert q.get() == "frame-a"
    assert q.depth == 0
    assert q.get() is None


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_invalid_maxsize_rejected_naming_value(bad: int) -> None:
    with pytest.raises(ValueError, match=str(bad)):
        LatestFrameQueue(maxsize=bad)


def test_default_maxsize_is_two() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue()
    assert q.maxsize == 2


# --- Overflow / retention ----------------------------------------------------


def test_overflow_maxsize1_drops_oldest() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=1)
    assert q.put("old") is False
    assert q.put("new") is True  # True == a stale frame was dropped
    assert q.depth == 1
    assert q.get() == "new"
    assert q.dropped == 1
    assert q.submitted == 2


def test_overflow_maxsize2_drops_oldest() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    assert q.put("a") is False
    assert q.put("b") is False
    assert q.put("c") is True
    assert q.depth == 2
    assert q.get() == "b"
    assert q.get() == "c"
    assert q.dropped == 1
    assert q.submitted == 3


def test_newest_retention_after_many_overflows() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    for i in range(10):
        q.put(i)
    assert q.depth == 2
    # Buffer holds the LAST maxsize frames in arrival order.
    assert q.get() == 8
    assert q.get() == 9
    assert q.get() is None
    assert q.submitted == 10
    assert q.dropped == 8


def test_fifo_ordering_among_retained() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.put("a")
    q.put("b")
    assert q.get() == "a"  # oldest retained first
    assert q.get() == "b"
    # Interleaved put/get preserves arrival order.
    q.put("c")
    q.put("d")
    q.put("e")  # drops "c"
    assert q.get() == "d"
    assert q.get() == "e"


def test_put_return_semantic_drop_flag() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    assert q.put(1) is False
    assert q.put(2) is False
    assert q.put(3) is True
    assert q.put(4) is True
    assert q.dropped == 2


def test_dropped_counter_exactness() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    n = 7
    for i in range(n):
        q.put(i)
    assert q.submitted == n
    assert q.dropped == n - 2
    assert q.depth == 2


def test_counters_start_at_zero() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    assert q.submitted == 0
    assert q.dropped == 0
    assert q.depth == 0


# --- clear -------------------------------------------------------------------


def test_clear_empties_depth_counters_monotonic() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.put("a")
    q.put("b")
    q.put("c")  # drops "a"
    submitted_before = q.submitted
    dropped_before = q.dropped
    q.clear()
    assert q.depth == 0
    assert q.get() is None
    assert q.submitted == submitted_before  # monotonic: not reset
    assert q.dropped == dropped_before
    # Queue still usable after clear.
    assert q.put("d") is False
    assert q.get() == "d"
    assert q.submitted == submitted_before + 1


def test_clear_on_empty_keeps_counters() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.clear()
    assert q.depth == 0
    assert q.submitted == 0
    assert q.dropped == 0


# --- close -------------------------------------------------------------------


def test_close_is_idempotent() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.close()
    q.close()
    assert q.closed is True


def test_put_after_close_raises() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.put("a")
    q.close()
    with pytest.raises(RuntimeError, match="queue is closed"):
        q.put("b")


def test_get_after_close_drains_then_none() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.put("a")
    q.put("b")
    q.close()
    assert q.get() == "a"
    assert q.get() == "b"
    assert q.get() is None
    assert q.get() is None


def test_get_on_empty_closed_returns_none() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.close()
    assert q.get() is None


def test_close_preserves_counters() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    q.put("a")
    q.put("b")
    q.put("c")
    submitted_before = q.submitted
    dropped_before = q.dropped
    q.close()
    assert q.submitted == submitted_before
    assert q.dropped == dropped_before


# --- repr --------------------------------------------------------------------


def test_repr_is_payload_free() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    secret_payload = "SUPER-SECRET-IMAGE-BYTES-xyz"
    q.put(secret_payload)
    text = repr(q)
    assert secret_payload not in text
    assert "maxsize" in text
    assert "depth" in text
    assert "submitted" in text
    assert "dropped" in text
    assert "closed" in text


def test_repr_large_object_payload_free() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=1)
    q.put(object())
    text = repr(q)
    assert "object at" not in text


# --- payload agnosticism ------------------------------------------------------


def test_payload_agnostic_identity() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=3)
    sentinel = object()
    q.put(sentinel)
    q.put(b"\x00\x01")
    q.put(12345)
    assert q.get() is sentinel
    assert q.get() == b"\x00\x01"
    assert q.get() == 12345


# --- depth invariant ----------------------------------------------------------


def test_depth_bounded_after_overflows() -> None:
    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    for i in range(50):
        q.put(i)
        assert 0 <= q.depth <= q.maxsize


# --- concurrency stress -------------------------------------------------------
# This test IS the P1-003 light perf measurement: thread counts, op counts,
# and wall time are recorded in docs/task-reports/P1-003.md.


def test_concurrent_producer_consumer_invariant_no_deadlock() -> None:
    n_producers = 2
    puts_per_producer = 2000
    total_puts = n_producers * puts_per_producer

    q: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    received = 0
    received_lock = threading.Lock()
    depth_violations: list[int] = []
    errors: list[BaseException] = []
    stop = threading.Event()

    def _producer(start: int) -> None:
        try:
            for i in range(puts_per_producer):
                q.put(start + i)
        except BaseException as exc:  # capture for main-thread assertion
            errors.append(exc)

    def _consumer() -> None:
        nonlocal received
        try:
            while not stop.is_set():
                item = q.get()
                if item is not None:
                    with received_lock:
                        received += 1
                depth = q.depth
                if not 0 <= depth <= q.maxsize:
                    depth_violations.append(depth)
        except BaseException as exc:  # capture for main-thread assertion
            errors.append(exc)

    producers = [
        threading.Thread(target=_producer, args=(p * puts_per_producer,))
        for p in range(n_producers)
    ]
    consumers = [threading.Thread(target=_consumer) for _ in range(2)]

    t0 = time.monotonic()
    for t in producers + consumers:
        t.start()
    for t in producers:
        t.join(timeout=30)
        assert not t.is_alive(), "producer thread deadlocked"
    stop.set()
    for t in consumers:
        t.join(timeout=30)
        assert not t.is_alive(), "consumer thread deadlocked"
    wall = time.monotonic() - t0
    assert wall < 60  # sanity: whole stress finishes promptly
    # Drain leftovers on the main thread.
    while q.get() is not None:
        with received_lock:
            received += 1

    assert not errors
    assert not depth_violations
    assert q.depth == 0  # fully drained
    assert q.submitted == total_puts
    # Invariant: every submitted frame was received, dropped, or still buffered.
    assert q.submitted == received + q.dropped + q.depth
    assert q.dropped == total_puts - received
    assert 0 <= q.depth <= q.maxsize
