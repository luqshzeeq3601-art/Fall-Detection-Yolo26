"""Unit tests for the RtspCapture seam (P1-002).

TDD RED-first suite covering the nine brief areas. Fakes only — no network
streams, devices, or real files are touched. Every credential value below is
a dummy placeholder used in-process only; nothing is written to disk.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from eldercare.common.logger import JsonFormatter, configure_logging
from eldercare.vision.stream.camera import CameraConfig
from eldercare.vision.stream.capture import RtspCapture, VideoCaptureLike

_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_RTSP_PLAIN = "rtsp://camera01.local:554/stream1"
_RTSP_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"


def _assert_no_raw_secrets(blob: str) -> None:
    assert _DUMMY_USER not in blob
    assert _DUMMY_PASS not in blob


def _make_config(url: str = _RTSP_PLAIN) -> CameraConfig:
    return CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=url)


class FakeCapture:
    """In-memory ``VideoCaptureLike`` double; no cv2, no I/O."""

    def __init__(
        self,
        *,
        opened: bool = True,
        read_result: tuple[bool, Any] | None = None,
        read_exc: BaseException | None = None,
    ) -> None:
        self._opened = opened
        self.read_result = read_result
        self.read_exc = read_exc
        self.release_calls = 0

    def isOpened(self) -> bool:  # noqa: N802 — mirrors cv2.VideoCapture API verbatim
        return self._opened

    def read(self) -> tuple[bool, Any]:
        if self.read_exc is not None:
            raise self.read_exc
        if self.read_result is not None:
            return self.read_result
        return True, object()

    def release(self) -> None:
        self.release_calls += 1


def _accept_url(factory: Callable[[VideoCaptureLike], None]) -> Callable[[str], FakeCapture]:
    """Wrap a per-fake assertion hook into a capture factory (proves DI typing)."""

    def _factory(url: str) -> FakeCapture:
        fake = FakeCapture(opened=True)
        factory(fake)
        return fake

    return _factory


@pytest.fixture()
def log_stream() -> Iterator[io.StringIO]:
    """Capture ``eldercare`` JSON log lines (mirrors P1-001 log-test style)."""
    logger = logging.getLogger("eldercare")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    configure_logging("INFO")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        handler.close()
        for saved in saved_handlers:
            logger.addHandler(saved)
        logger.setLevel(saved_level)


# --- Area 1: open success ----------------------------------------------------


def test_open_success_returns_true_sets_state() -> None:
    fake = FakeCapture(opened=True)
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.is_opened is False  # starts closed
    assert cap.last_error is None
    assert cap.open() is True
    assert cap.is_opened is True
    assert cap.last_error is None


def test_open_passes_configured_url_to_factory() -> None:
    seen: list[str] = []

    def _factory(url: str) -> FakeCapture:
        seen.append(url)
        return FakeCapture(opened=True)

    cap = RtspCapture(_make_config(), capture_factory=_factory)
    assert cap.open() is True
    assert seen == [_RTSP_PLAIN]


def test_di_seam_accepts_protocol_typed_factory() -> None:
    received: list[VideoCaptureLike] = []

    def _hook(fake: VideoCaptureLike) -> None:
        received.append(fake)

    cap = RtspCapture(_make_config(), capture_factory=_accept_url(_hook))
    assert cap.open() is True
    assert len(received) == 1


# --- Area 2: open failure (isOpened False) -----------------------------------


def test_open_failure_returns_false_with_error_no_throw() -> None:
    cap = RtspCapture(_make_config(), capture_factory=lambda url: FakeCapture(opened=False))
    assert cap.open() is False
    assert cap.is_opened is False
    assert isinstance(cap.last_error, str) and cap.last_error


# --- Area 3: factory raises ---------------------------------------------------


def test_factory_raises_returns_false_password_absent() -> None:
    boom = RuntimeError(f"connect failed for {_RTSP_CREDS} token=hunter2")

    def _factory(url: str) -> FakeCapture:
        raise boom

    cap = RtspCapture(_make_config(_RTSP_CREDS), capture_factory=_factory)
    assert cap.open() is False
    assert cap.is_opened is False
    assert isinstance(cap.last_error, str) and cap.last_error
    _assert_no_raw_secrets(cap.last_error)
    assert "hunter2" not in cap.last_error


# --- Area 4: read success -----------------------------------------------------


def test_read_success_passes_frame_through() -> None:
    sentinel = object()
    fake = FakeCapture(opened=True, read_result=(True, sentinel))
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is True
    ok, frame = cap.read()
    assert ok is True
    assert frame is sentinel


# --- Area 5: read failures ----------------------------------------------------


def test_read_failure_flag_returns_false_none() -> None:
    fake = FakeCapture(opened=True, read_result=(False, None))
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is True
    ok, frame = cap.read()
    assert ok is False
    assert frame is None
    assert isinstance(cap.last_error, str) and cap.last_error


def test_read_raises_returns_false_none_sanitized() -> None:
    fake = FakeCapture(opened=True, read_exc=RuntimeError("boom decode failure"))
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is True
    ok, frame = cap.read()
    assert ok is False
    assert frame is None
    assert isinstance(cap.last_error, str) and "boom" in cap.last_error


def test_read_when_never_opened_returns_false_none() -> None:
    cap = RtspCapture(_make_config(), capture_factory=lambda url: FakeCapture(opened=True))
    ok, frame = cap.read()
    assert ok is False
    assert frame is None


def test_read_after_release_returns_false_none() -> None:
    fake = FakeCapture(opened=True)
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is True
    cap.release()
    ok, frame = cap.read()
    assert ok is False
    assert frame is None


# --- Area 6: release idempotency ----------------------------------------------


def test_release_idempotent_triple() -> None:
    fake = FakeCapture(opened=True)
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is True
    cap.release()
    cap.release()
    cap.release()
    assert fake.release_calls == 1
    assert cap.is_opened is False


def test_release_without_open_no_throw() -> None:
    cap = RtspCapture(_make_config(), capture_factory=lambda url: FakeCapture(opened=True))
    cap.release()  # must not raise; handle stays dropped
    assert cap.is_opened is False
    cap.release()


def test_release_after_failed_open_no_throw() -> None:
    fake = FakeCapture(opened=False)
    cap = RtspCapture(_make_config(), capture_factory=lambda url: fake)
    assert cap.open() is False
    assert cap.is_opened is False  # failed open holds no seam handle
    calls_after_open = fake.release_calls  # failed-open path already cleaned the backend
    cap.release()  # explicit release after failed open must not raise
    assert cap.is_opened is False
    assert fake.release_calls == calls_after_open  # no double-release of the backend
    cap.release()


# --- Area 7: context manager --------------------------------------------------


def test_context_manager_releases_on_exit() -> None:
    fake = FakeCapture(opened=True)
    with RtspCapture(_make_config(), capture_factory=lambda url: fake) as cap:
        assert cap.is_opened is True
        assert fake.release_calls == 0
    assert fake.release_calls == 1
    assert cap.is_opened is False


def test_context_manager_open_failure_documented() -> None:
    """Enter never raises on open failure; body sees a closed capture."""
    with RtspCapture(_make_config(), capture_factory=lambda url: FakeCapture(opened=False)) as cap:
        assert cap.is_opened is False
        ok, frame = cap.read()
        assert ok is False
        assert frame is None
    cap.release()  # exit path released cleanly; extra release still safe


# --- Area 8: credential safety end-to-end -------------------------------------


def test_repr_and_str_show_id_and_state_never_url() -> None:
    cfg = _make_config(_RTSP_CREDS)
    cap = RtspCapture(cfg, capture_factory=lambda url: FakeCapture(opened=True))
    assert cap.open() is True
    for text in (repr(cap), str(cap)):
        _assert_no_raw_secrets(text)
        assert "camera01.local" not in text  # URL absent entirely, not merely redacted
        assert "cam-01" in text
        assert "True" in text
    cap.release()
    _assert_no_raw_secrets(repr(cap))
    assert "False" in repr(cap)


def test_credential_safety_end_to_end(log_stream: io.StringIO) -> None:
    cfg = _make_config(_RTSP_CREDS)
    boom = RuntimeError(f"connect failed for {_RTSP_CREDS} token=hunter2")

    def _raising(url: str) -> FakeCapture:
        raise boom

    cap = RtspCapture(cfg, capture_factory=_raising)
    assert cap.open() is False
    assert cap.last_error is not None
    _assert_no_raw_secrets(cap.last_error)

    cap2 = RtspCapture(
        cfg,
        capture_factory=lambda url: FakeCapture(
            opened=True, read_exc=RuntimeError(f"decode failed for {_RTSP_CREDS}")
        ),
    )
    assert cap2.open() is True
    ok, frame = cap2.read()
    assert (ok, frame) == (False, None)
    assert cap2.last_error is not None
    _assert_no_raw_secrets(cap2.last_error)
    _assert_no_raw_secrets(repr(cap2))
    _assert_no_raw_secrets(str(cap2))

    blob = log_stream.getvalue()
    assert blob, "expected JSON log lines"
    _assert_no_raw_secrets(blob)
    assert "hunter2" not in blob
    assert "capture.open_failed" in blob
    assert "capture.read_failed" in blob


def test_happy_path_logs_credential_free(log_stream: io.StringIO) -> None:
    cap = RtspCapture(
        _make_config(_RTSP_CREDS), capture_factory=lambda url: FakeCapture(opened=True)
    )
    assert cap.open() is True
    cap.release()
    blob = log_stream.getvalue()
    assert "capture.opened" in blob
    assert "capture.released" in blob
    _assert_no_raw_secrets(blob)
    assert "camera01.local" not in blob


# --- Area 9: default factory is cv2-backed ------------------------------------


def test_default_factory_is_cv2_backed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``cv2.VideoCapture`` itself: the default path must call it with
    the configured URL. Mocking (rather than opening a nonexistent file) keeps
    the test deterministic and backend-independent — no filesystem, backend,
    or warning-timing coupling — while still proving cv2 wiring + graceful
    ``False`` on ``isOpened()=False``."""
    import cv2

    seen: list[str] = []
    fake = FakeCapture(opened=True)

    def _fake_video_capture(url: str) -> FakeCapture:
        seen.append(url)
        return fake

    monkeypatch.setattr(cv2, "VideoCapture", _fake_video_capture)
    cap = RtspCapture(_make_config())
    assert cap.open() is True
    assert seen == [_RTSP_PLAIN]
    assert cap.is_opened is True


def test_default_factory_open_failure_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default path with ``isOpened()=False`` returns ``False``, no throw."""
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda url: FakeCapture(opened=False))
    cap = RtspCapture(_make_config())
    assert cap.open() is False
    assert cap.is_opened is False


# --- Failure-state clearing ---------------------------------------------------


def test_last_error_cleared_on_successful_open_and_read() -> None:
    attempts = {"n": 0}
    sentinel = object()

    def _factory(url: str) -> FakeCapture:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return FakeCapture(opened=False)
        return FakeCapture(opened=True, read_result=(False, None))

    cap = RtspCapture(_make_config(), capture_factory=_factory)
    assert cap.open() is False
    assert cap.last_error is not None
    assert cap.open() is True
    assert cap.last_error is None
    ok, frame = cap.read()
    assert (ok, frame) == (False, None)  # read failure re-arms last_error
    assert cap.last_error is not None
    cap._handle.read_result = (True, sentinel)  # type: ignore[union-attr]
    ok, frame = cap.read()
    assert ok is True and frame is sentinel
    assert cap.last_error is None


# --- P1-003 minor #4: failed-open cleanup stays silent -------------------------
# Documents the aligned behavior: failed-open cleanup ``release()`` errors
# are discarded so the open-failure ``last_error`` is preserved, while
# explicit ``release()`` arms ``last_error`` on backend errors.


class _FailingReleaseCapture(FakeCapture):
    """Fake whose backend ``release()`` always raises."""

    def __init__(self, *, opened: bool = True, is_opened_exc: BaseException | None = None) -> None:
        super().__init__(opened=opened)
        self._is_opened_exc = is_opened_exc

    def isOpened(self) -> bool:  # noqa: N802 — mirrors cv2.VideoCapture API verbatim
        if self._is_opened_exc is not None:
            raise self._is_opened_exc
        return super().isOpened()

    def release(self) -> None:
        raise RuntimeError("cleanup release boom")


def test_failed_open_cleanup_release_error_preserves_open_last_error() -> None:
    """``isOpened()=False`` + raising cleanup release: no throw, open-failure kept."""
    cap = RtspCapture(
        _make_config(), capture_factory=lambda url: _FailingReleaseCapture(opened=False)
    )
    assert cap.open() is False
    assert cap.is_opened is False
    assert cap.last_error == "capture open failed: backend reported isOpened()=False"
    assert "cleanup release boom" not in (cap.last_error or "")


def test_failed_open_isopened_exc_cleanup_release_error_preserved() -> None:
    """``isOpened()`` raising + raising cleanup release: no throw, open-failure kept."""
    boom = RuntimeError("backend isOpened failure")

    def _factory(url: str) -> _FailingReleaseCapture:
        return _FailingReleaseCapture(is_opened_exc=boom)

    cap = RtspCapture(_make_config(), capture_factory=_factory)
    assert cap.open() is False
    assert cap.is_opened is False
    assert isinstance(cap.last_error, str) and "backend isOpened failure" in cap.last_error
    assert "cleanup release boom" not in (cap.last_error or "")


def test_explicit_release_backend_error_arms_last_error() -> None:
    """Explicit ``release()`` backend ``Exception`` arms ``last_error`` (vs silent cleanup)."""
    cap = RtspCapture(
        _make_config(), capture_factory=lambda url: _FailingReleaseCapture(opened=True)
    )
    assert cap.open() is True
    cap.release()  # must not raise; arms sanitized last_error
    assert cap.is_opened is False
    assert cap.last_error is not None and "cleanup release boom" in cap.last_error
    _assert_no_raw_secrets(cap.last_error)
