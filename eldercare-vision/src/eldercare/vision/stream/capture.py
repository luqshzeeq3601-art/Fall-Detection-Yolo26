"""RTSP capture seam over :class:`CameraConfig` (P1-002).

Lifecycle contract (explicit open/read/release; no reconnect, no queues):

- Construct ``RtspCapture(config, capture_factory=None)`` — starts closed
  with ``last_error`` unset. The default factory is ``cv2.VideoCapture``,
  resolved by attribute lookup at each :meth:`open` call so tests can
  monkeypatch ``cv2.VideoCapture``. Pass any
  ``Callable[[str], VideoCaptureLike]`` fake for unit tests (no cv2 needed).
- ``open() -> bool`` — builds a capture via the factory with the configured
  URL and returns the backend ``isOpened()`` flag. A prior held handle is
   released first. Factory ``Exception``s and ``isOpened() == False`` yield
   ``False`` plus a sanitized ``last_error`` — never raises for open-failure
   ``Exception``s (``BaseException`` propagates).
- ``read() -> tuple[bool, ndarray | None]`` — ``(False, None)`` when closed,
  on backend failure flags, or on backend exceptions — never raises for
  read-failure. Success passes the backend frame object through untouched.
- ``release() -> None`` — idempotent: safe xN, safe when never opened, safe
  after a failed open; drops the handle in all cases.
- ``is_opened`` reflects seam state (a handle is held), NOT a live backend
  poll — no per-call backend I/O. ``last_error`` is cleared on every
  successful open/read and holds sanitized text after failures.
- Context manager: ``__enter__`` opens and returns ``self`` (never raises
  for open-failure — check ``is_opened`` inside the block); ``__exit__``
  releases. Exceptions from the block body propagate (``__exit__`` is falsy).

Failure semantics: open/read return-``False``-never-raise for ``Exception``
failures. ``BaseException`` (e.g. ``KeyboardInterrupt``/``SystemExit``
cancellation) is never swallowed and propagates by design — catching it
would be an anti-pattern. A propagating ``BaseException`` object itself may
carry the raw factory message; this module never logs or stores it (only
the caller's own exception object), so never log a cancelled-open's
exception raw.

Deliberate differences from raw ``cv2.VideoCapture``:

- Errors are sanitized via P0-005 ``sanitize_exception_message`` so backend
  messages embedding the RTSP URL can never surface raw.
- ``repr``/``str`` carry ``camera_id`` + opened state ONLY — the URL is
  absent entirely (stronger than P1-001's redacted repr: not even the host
  is needed to correlate capture state; ``camera_id`` suffices).
- Dependency-injection seam (``VideoCaptureLike`` protocol + factory) so
  tests never touch networks, devices, or files.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol

import cv2
import numpy as np

from eldercare.common.logger import get_logger
from eldercare.common.redaction import sanitize_exception_message
from eldercare.vision.stream.camera import CameraConfig


class VideoCaptureLike(Protocol):
    """Minimal structural seam over ``cv2.VideoCapture`` (method names mirror
    the installed OpenCV build verbatim: ``isOpened``/``read``/``release``)."""

    def isOpened(self) -> bool:  # noqa: N802 — mirrors cv2.VideoCapture API verbatim
        """Return whether the backend reports the stream as opened."""
        ...

    def read(self) -> tuple[bool, Any]:
        """Return ``(ok, frame)`` like ``cv2.VideoCapture.read``."""
        ...

    def release(self) -> None:
        """Release the backend handle."""
        ...


class RtspCapture:
    """Explicit-lifecycle RTSP capture handle built from a ``CameraConfig``.

    Threading model: NOT thread-safe — a single capture-loop thread must own
    each instance (``open``/``read``/``release`` require external sync if
    shared). The thread-safe handoff to consumers is the queue
    (``LatestFrameQueue``), not the capture.
    """

    def __init__(
        self,
        config: CameraConfig,
        capture_factory: Callable[[str], VideoCaptureLike] | None = None,
    ) -> None:
        self._config = config
        self._capture_factory = capture_factory
        self._handle: VideoCaptureLike | None = None
        self._last_error: str | None = None
        self._logger = get_logger("vision", component="stream.capture", camera_id=config.camera_id)

    @property
    def is_opened(self) -> bool:
        """Whether the seam currently holds a capture handle."""
        return self._handle is not None

    @property
    def last_error(self) -> str | None:
        """Sanitized text of the last open/read failure, else ``None``."""
        return self._last_error

    def open(self) -> bool:
        """Build the backend capture; return its ``isOpened()`` flag.

        Never raises for open-failure ``Exception`` subclasses: factory/
        `isOpened` ``Exception``s and ``isOpened() == False`` all yield
        ``False`` with ``last_error`` set. ``BaseException`` propagates.
        """
        if self._handle is not None:
            self.release()
        factory = self._capture_factory if self._capture_factory is not None else cv2.VideoCapture
        try:
            handle = factory(self._config.rtsp_url)
        except Exception as exc:
            self._last_error = sanitize_exception_message(str(exc))
            self._logger.warning(
                "capture open failed: %s", self._last_error, extra={"event": "capture.open_failed"}
            )
            return False
        self._handle = handle
        try:
            opened = bool(handle.isOpened())
        except Exception as exc:
            self._last_error = sanitize_exception_message(str(exc))
            self._handle = None
            self._logger.warning(
                "capture open failed: %s", self._last_error, extra={"event": "capture.open_failed"}
            )
            try:
                handle.release()
            except Exception:
                # Cleanup release must not overwrite the open-failure
                # ``last_error`` set above; the open already reports ``False``.
                pass
            return False
        if not opened:
            self._last_error = "capture open failed: backend reported isOpened()=False"
            self._handle = None
            self._logger.warning(
                "capture open failed: %s", self._last_error, extra={"event": "capture.open_failed"}
            )
            try:
                handle.release()
            except Exception:
                # Cleanup release must not overwrite the open-failure
                # ``last_error`` set above; the open already reports ``False``.
                pass
            return False
        self._last_error = None
        self._logger.info("capture opened", extra={"event": "capture.opened"})
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Return ``(True, frame)`` on success, ``(False, None)`` otherwise.

        Never raises for read-failure ``Exception`` subclasses (closed
        capture, backend failure flag, or backend ``Exception``).
        ``BaseException`` propagates.
        """
        handle = self._handle
        if handle is None:
            self._last_error = "capture read failed: capture is not open"
            self._logger.warning(
                "capture read failed: %s", self._last_error, extra={"event": "capture.read_failed"}
            )
            return False, None
        try:
            ok, frame = handle.read()
        except Exception as exc:
            self._last_error = sanitize_exception_message(str(exc))
            self._logger.warning(
                "capture read failed: %s", self._last_error, extra={"event": "capture.read_failed"}
            )
            return False, None
        if not ok:
            self._last_error = "capture read failed: backend reported failure"
            self._logger.warning(
                "capture read failed: %s", self._last_error, extra={"event": "capture.read_failed"}
            )
            return False, None
        self._last_error = None
        return True, frame

    def release(self) -> None:
        """Drop the handle; idempotent and safe when never opened.

        A backend ``release()`` ``Exception`` arms ``last_error`` (unlike the
        failed-open cleanup path, which stays silent to preserve the
        open-failure ``last_error``).
        """
        handle, self._handle = self._handle, None
        if handle is None:
            self._logger.info("capture released", extra={"event": "capture.released"})
            return
        try:
            handle.release()
        except Exception as exc:
            self._last_error = sanitize_exception_message(str(exc))
        self._logger.info("capture released", extra={"event": "capture.released"})

    def __enter__(self) -> RtspCapture:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def __repr__(self) -> str:
        return f"RtspCapture(camera_id={self._config.camera_id!r}, opened={self.is_opened!r})"

    def __str__(self) -> str:
        return self.__repr__()
