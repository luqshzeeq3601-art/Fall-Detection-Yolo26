"""Unit tests for capture telemetry (P1-006).

TDD RED-first suite covering the eleven brief areas. Fake clock ONLY —
zero real sleeps (no ``time.sleep`` anywhere in this file); every timestamp
is injected explicitly or driven by ``FakeClock``. All credential values are
dummy placeholders used in-process only; nothing is written to disk.

On-call questions this snapshot answers (observability skill step 1):
  1. What capture FPS is this camera actually delivering right now?
  2. Is the capture queue saturated (depth / dropped frames)?
  3. Is the stream healthy — when was the last frame, how long silent?
  4. How many reconnect attempts / consecutive failures have occurred?
Every asserted signal maps to one of these; anything else is out of scope.

Area map (brief §Tests):
   1. empty snapshot: all-``None``/zero contract exact
   2. scripted frames → EXACT fps values incl. strict-``>`` boundary
   3. single frame → ``fps None`` (no fabrication)
   4. pruning: old frames excluded from fps AND deque length shrinks
   5. bounded memory: 100k rapid notes → ``len <= MAX`` cap
   6. live aggregation: real trio mutated via their own APIs → exact mirror
   7. read-only proof: component state identical before/after 100 snapshots
   8. thread smoke: concurrent ``note_frame`` + ``snapshot``, join timeouts
   9. credential-free: snapshot dict + repr contain no password/token/URL
  10. strict JSON: ``json.dumps(..., allow_nan=False)`` on all shapes
  11. invalid inputs: bad window, NaN/negative note timestamps → ValueError
"""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

# RED: this import fails until telemetry.py exists.
from eldercare.vision.stream.camera import CameraConfig
from eldercare.vision.stream.health import CameraHealthState, StreamHealthMonitor
from eldercare.vision.stream.queue import LatestFrameQueue
from eldercare.vision.stream.reconnect import ReconnectController
from eldercare.vision.stream.telemetry import (
    MAX_FRAME_TIMESTAMPS,
    CaptureSnapshot,
    CaptureTelemetry,
)

_RTSP_PLAIN = "rtsp://camera01.local:554/stream1"
_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_DUMMY_TOKEN = "dummy-token-abc"
_RTSP_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"


def _assert_no_raw_secrets(blob: str) -> None:
    assert _DUMMY_USER not in blob
    assert _DUMMY_PASS not in blob
    assert _DUMMY_TOKEN not in blob
    assert "rtsp://" not in blob


class FakeClock:
    """Deterministic injectable clock (no real time)."""

    def __init__(self, start: float = 0.0) -> None:
        self.now: float = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> float:
        self.now += dt
        return self.now


class FakeSleep:
    """Recording sleep double: stores each requested delay, never sleeps."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, delay: float) -> None:
        self.calls.append(delay)


class FakeCapture:
    """Scripted ``open()`` double; repeats the last result when exhausted."""

    def __init__(self, script: list[bool]) -> None:
        if not script:
            raise ValueError("script must be a non-empty list of open() results")
        self._script: list[bool] = list(script)
        self.open_calls: int = 0

    def open(self) -> bool:
        self.open_calls += 1
        index = min(self.open_calls - 1, len(self._script) - 1)
        return self._script[index]


def _make_config(url: str = _RTSP_PLAIN, camera_id: str = "cam-01") -> CameraConfig:
    return CameraConfig(camera_id=camera_id, name="Lobby", rtsp_url=url)


def _make_trio(
    queue_maxsize: int = 2,
) -> tuple[LatestFrameQueue[Any], StreamHealthMonitor, ReconnectController, FakeClock, FakeSleep]:
    """Build a real queue/health/reconnect trio wired to fakes (zero sleeps)."""
    clock = FakeClock()
    queue: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=queue_maxsize)
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    capture = FakeCapture([False])
    sleep = FakeSleep()
    controller = ReconnectController(_make_config(), capture, health, sleep=sleep, clock=clock)
    return queue, health, controller, clock, sleep


# --- Area 1: empty snapshot ----------------------------------------------------


def test_1_empty_snapshot_all_none_zero_contract() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(100.0))
    snap = tel.snapshot(now=100.0)
    assert isinstance(snap, CaptureSnapshot)
    assert snap.camera_id == "cam-01"
    assert snap.captured_at == pytest.approx(100.0)
    assert snap.capture_fps is None  # unknown, never fabricated
    assert snap.frames_received == 0
    assert snap.queue_submitted is None
    assert snap.queue_dropped is None
    assert snap.queue_depth is None  # unknown, not zero
    assert snap.reconnect_attempts is None
    assert snap.reconnect_failures is None
    assert snap.health_state is None
    assert snap.last_frame_at is None
    assert snap.seconds_since_last_frame is None
    assert tel.frame_window_size == 0


def test_1b_snapshot_is_frozen_and_dict_preserves_nones() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(100.0))
    snap = tel.snapshot(now=100.0)
    with pytest.raises(FrozenInstanceError):
        snap.frames_received = 5  # type: ignore[misc]
    assert snap.to_dict() == {
        "camera_id": "cam-01",
        "captured_at": 100.0,
        "capture_fps": None,
        "frames_received": 0,
        "queue_submitted": None,
        "queue_dropped": None,
        "queue_depth": None,
        "reconnect_attempts": None,
        "reconnect_failures": None,
        "health_state": None,
        "last_frame_at": None,
        "seconds_since_last_frame": None,
    }


def test_1c_clock_defaults_used_when_now_omitted() -> None:
    clock = FakeClock(50.0)
    tel = CaptureTelemetry(camera_id="cam-01", clock=clock)
    tel.note_frame()  # None -> clock() == 50.0
    snap = tel.snapshot()  # None -> clock() == 50.0
    assert snap.captured_at == pytest.approx(50.0)
    assert snap.frames_received == 1
    assert snap.capture_fps is None  # single frame is not a rate


# --- Area 2: exact fps ---------------------------------------------------------


def test_2a_ten_frames_over_five_seconds_is_exactly_two() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    for i in range(10):
        tel.note_frame(0.5 + 0.5 * i)  # 0.5 .. 5.0
    snap = tel.snapshot(now=5.0)  # window (0, 5]: all 10 inside
    assert snap.capture_fps == 2.0
    assert snap.frames_received == 10


def test_2b_window_boundary_is_strict_greater() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    tel.note_frame(5.0)  # exactly now - window for now=10.0 -> EXCLUDED
    tel.note_frame(6.0)
    tel.note_frame(7.0)
    snap = tel.snapshot(now=10.0)  # window (5, 10]: only 6.0, 7.0 count
    assert snap.capture_fps == 0.4  # 2 / 5.0; would be 0.6 if boundary leaked in
    assert snap.frames_received == 3


def test_2c_boundary_single_remaining_frame_is_none() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    tel.note_frame(5.0)
    snap = tel.snapshot(now=10.0)  # window (5, 10]: boundary excluded -> zero in window
    assert snap.capture_fps is None
    assert snap.frames_received == 1


# --- Area 3: single frame ------------------------------------------------------


def test_3_single_frame_fps_is_none_no_fabrication() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    tel.note_frame(3.0)
    snap = tel.snapshot(now=3.0)
    assert snap.capture_fps is None
    assert snap.frames_received == 1
    assert snap.to_dict()["capture_fps"] is None


# --- Area 4: pruning -----------------------------------------------------------


def test_4_old_frames_excluded_and_deque_shrinks() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    for t in range(10):
        tel.note_frame(float(t))  # 0.0 .. 9.0
    assert tel.frames_received == 10
    assert tel.frame_window_size == 5  # pruned to (4, 9]: 5.0 .. 9.0
    snap = tel.snapshot(now=9.0)
    assert snap.capture_fps == 1.0  # 5 / 5.0; stale 0.0 .. 4.0 excluded
    assert tel.frame_window_size == 5


def test_4b_out_of_order_accepted_and_pruned_unlike_health() -> None:
    # Frames are observations, not state: an older timestamp is accepted
    # (health would IGNORE it) and only window-pruning applies.
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    tel.note_frame(10.0)
    tel.note_frame(9.0)  # older, but accepted
    assert tel.frames_received == 2
    snap = tel.snapshot(now=10.0)  # window (5, 10]: both inside
    assert snap.capture_fps == 0.4


# --- Area 5: bounded memory ----------------------------------------------------


def test_5_100k_rapid_notes_stay_capped() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    assert MAX_FRAME_TIMESTAMPS == 16384  # documented safety cap, pinned
    for _ in range(100_000):
        tel.note_frame(7.0)  # frozen timestamp: no window pruning, cap must bind
    assert tel.frames_received == 100_000
    assert tel.frame_window_size <= MAX_FRAME_TIMESTAMPS
    assert tel.frame_window_size == MAX_FRAME_TIMESTAMPS
    snap = tel.snapshot(now=7.0)
    assert snap.capture_fps == MAX_FRAME_TIMESTAMPS / 5.0  # fps sanity, finite float
    assert isinstance(snap.capture_fps, float)
    json.dumps(snap.to_dict(), allow_nan=False)  # strict-JSON-safe even at the cap


# --- Area 6: live aggregation --------------------------------------------------


def test_6_live_trio_mirrors_exactly() -> None:
    queue, health, controller, clock, _ = _make_trio()
    queue.put("a")
    queue.put("b")
    queue.put("c")  # maxsize=2 -> submitted 3, dropped 1, depth 2
    assert health.notify_frame(20.0) is not None
    assert controller.attempt() is False
    assert controller.attempt() is False  # attempts 2, consecutive_failures 2
    tel = CaptureTelemetry(
        camera_id="cam-01", queue=queue, health=health, reconnect=controller, clock=clock
    )
    tel.note_frame(20.0)
    snap = tel.snapshot(now=21.0)
    assert snap.queue_submitted == queue.submitted == 3
    assert snap.queue_dropped == queue.dropped == 1
    assert snap.queue_depth == queue.depth == 2
    assert snap.reconnect_attempts == controller.attempts == 2
    assert snap.reconnect_failures == controller.consecutive_failures == 2
    assert snap.health_state == health.state.value == CameraHealthState.ONLINE.value == "online"
    assert snap.last_frame_at == health.last_frame_at == pytest.approx(20.0)
    assert snap.seconds_since_last_frame == pytest.approx(1.0)
    assert snap.capture_fps is None  # single telemetry frame: unknown
    assert snap.frames_received == 1


def test_6b_seconds_since_none_when_no_frame_yet() -> None:
    _, health, _, clock, _ = _make_trio()
    tel = CaptureTelemetry(camera_id="cam-01", health=health, clock=clock)
    snap = tel.snapshot(now=42.0)
    assert snap.health_state == "unknown"
    assert snap.last_frame_at is None
    assert snap.seconds_since_last_frame is None  # no last frame -> unknown, not zero


# --- Area 7: read-only proof ---------------------------------------------------


def test_7_snapshot_never_mutates_components() -> None:
    queue, health, controller, clock, _ = _make_trio()
    queue.put("a")
    queue.put("b")
    queue.put("c")
    assert health.notify_frame(20.0) is not None
    assert controller.attempt() is False
    tel = CaptureTelemetry(
        camera_id="cam-01", queue=queue, health=health, reconnect=controller, clock=clock
    )
    tel.note_frame(20.0)

    def _component_state() -> tuple[Any, ...]:
        return (
            queue.submitted,
            queue.dropped,
            queue.depth,
            health.state,
            health.last_frame_at,
            controller.attempts,
            controller.consecutive_failures,
        )

    before = _component_state()
    snaps = [tel.snapshot(now=21.0) for _ in range(100)]
    assert _component_state() == before  # read-only: identical after 100 snapshots
    assert all(s == snaps[0] for s in snaps)  # deterministic repeated reads
    assert queue.get() == "b"  # queue contents undisturbed (retained "b", "c")
    assert queue.get() == "c"


# --- Area 8: thread smoke ------------------------------------------------------


def test_8_concurrent_note_and_snapshot_is_clean() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(0.0), fps_window_seconds=5.0)
    errors: list[BaseException] = []
    noters = 4
    notes_each = 250
    snapshots_each = 250

    def _note(base: float) -> None:
        try:
            for i in range(notes_each):
                tel.note_frame(base + float(i))
        except BaseException as exc:
            errors.append(exc)

    def _snap() -> None:
        try:
            for _ in range(snapshots_each):
                snap = tel.snapshot(now=1_000_000.0)
                assert snap.frames_received >= 0
                assert snap.capture_fps is None or math.isfinite(snap.capture_fps)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_note, args=(10_000.0 * k,)) for k in range(noters)]
    threads += [threading.Thread(target=_snap) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "telemetry thread deadlocked"
    assert not errors
    final = tel.snapshot(now=1_000_000.0)
    assert final.frames_received == noters * notes_each  # self-consistent: no lost notes


# --- Area 9: credential-free ---------------------------------------------------


def test_9_snapshot_and_repr_carry_no_secrets() -> None:
    config = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    clock = FakeClock()
    queue: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    queue.put("frame")
    health = StreamHealthMonitor(camera_id="cam-01", clock=clock)
    assert health.notify_frame(5.0) is not None
    capture = FakeCapture([False])
    controller = ReconnectController(config, capture, health, sleep=FakeSleep(), clock=clock)
    assert controller.attempt() is False
    tel = CaptureTelemetry(
        camera_id=config.camera_id,
        queue=queue,
        health=health,
        reconnect=controller,
        clock=clock,
    )
    tel.note_frame(5.0)
    snap = tel.snapshot(now=6.0)
    blob = json.dumps(snap.to_dict())
    _assert_no_raw_secrets(blob)
    assert "camera01.local" not in blob  # no component exposes host; must not appear
    text = repr(tel)
    assert "cam-01" in text
    _assert_no_raw_secrets(text)
    assert "camera01.local" not in text
    assert "@" not in text  # no userinfo anywhere


# --- Area 10: strict JSON ------------------------------------------------------


def test_10_strict_json_on_all_shapes() -> None:
    empty = CaptureTelemetry(camera_id="cam-01", clock=FakeClock()).snapshot(now=1.0)
    assert json.loads(json.dumps(empty.to_dict(), allow_nan=False)) == empty.to_dict()

    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    for i in range(10):
        tel.note_frame(0.5 + 0.5 * i)
    populated = tel.snapshot(now=5.0)
    assert populated.capture_fps == 2.0
    assert json.loads(json.dumps(populated.to_dict(), allow_nan=False)) == populated.to_dict()

    pruned = tel.snapshot(now=1_000.0)  # everything stale -> fps None
    assert pruned.capture_fps is None
    assert json.loads(json.dumps(pruned.to_dict(), allow_nan=False)) == pruned.to_dict()


def test_10b_fps_never_nan_or_inf() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    for i in range(1000):
        tel.note_frame(100.0 + i * 0.001)
    snap = tel.snapshot(now=101.0)
    assert snap.capture_fps is not None
    assert math.isfinite(snap.capture_fps)
    json.dumps(snap.to_dict(), allow_nan=False)


# --- Area 11: invalid inputs ---------------------------------------------------


@pytest.mark.parametrize("bad", [0.0, -1.0, -5.0, math.nan, math.inf, -math.inf])
def test_11a_bad_window_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="fps_window_seconds"):
        CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0, -0.5])
def test_11b_bad_note_timestamps_rejected(bad: float) -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock())
    with pytest.raises(ValueError):
        tel.note_frame(bad)
    assert tel.frames_received == 0  # rejected note changes nothing
    assert tel.frame_window_size == 0


@pytest.mark.parametrize("bad", [True, "7.0", object(), [1.0]])
def test_11c_non_numeric_note_timestamps_rejected(bad: Any) -> None:
    # NOTE: ``None`` is deliberately absent here — ``note_frame(None)`` means
    # "read the clock" per the contract (covered by test_1c), not an error.
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock())
    with pytest.raises(ValueError):
        tel.note_frame(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -1.0])
def test_11d_bad_snapshot_now_rejected(bad: float) -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock())
    with pytest.raises(ValueError):
        tel.snapshot(now=bad)


# --- Contract extras: repr, clock validation -----------------------------------


def test_repr_carries_ids_and_scalars_without_urls() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock(), fps_window_seconds=5.0)
    for i in range(10):
        tel.note_frame(0.5 + 0.5 * i)
    queue: LatestFrameQueue[Any] = LatestFrameQueue(maxsize=2)
    queue.put("x")
    health = StreamHealthMonitor(camera_id="cam-01", clock=FakeClock())
    assert health.notify_frame(5.0) is not None
    tel_attached = CaptureTelemetry(
        camera_id="cam-01", queue=queue, health=health, clock=FakeClock(5.0)
    )
    tel_attached.note_frame(4.0)
    tel_attached.note_frame(5.0)
    text = repr(tel_attached)
    assert "cam-01" in text
    assert "frames_received=2" in text
    assert "://" not in text
    assert "http" not in text.lower()


def test_note_frame_rejects_bool_like_health() -> None:
    tel = CaptureTelemetry(camera_id="cam-01", clock=FakeClock())
    with pytest.raises(ValueError):
        tel.note_frame(True)
    assert tel.frames_received == 0


def test_typed_clock_factory() -> None:
    clock: Callable[[], float] = FakeClock(1.0)
    tel = CaptureTelemetry(camera_id="cam-typed", clock=clock)
    snap = tel.snapshot()
    assert snap.captured_at == pytest.approx(1.0)
    assert snap.camera_id == "cam-typed"
