"""Unit tests for structured JSON logging (P0-006).

TDD RED-first suite covering the nine brief areas. Every credential value
below is a dummy placeholder used in-process only; nothing is written to disk.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime

import pytest

from eldercare.common.logger import JsonFormatter, configure_logging, get_logger

_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_DUMMY_TOKEN = "dummy-token-value-xyz"
_RTSP_WITH_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"
_PG_WITH_CREDS = f"postgresql://{_DUMMY_USER}:{_DUMMY_PASS}@postgres:5432/eldercare_dummy"

_STABLE_KEYS = {
    "timestamp",
    "level",
    "logger",
    "service",
    "component",
    "event",
    "message",
    "extra",
}
_OPTIONAL_KEYS = {"camera_id", "incident_id", "error"}


@pytest.fixture
def eldercare_logger() -> logging.Logger:
    """Isolate the shared ``eldercare`` logger around each test."""
    logger = logging.getLogger("eldercare")
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    for handler in saved_handlers:
        logger.removeHandler(handler)
    configure_logging("INFO")
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    for handler in saved_handlers:
        logger.addHandler(handler)
    logger.setLevel(saved_level)


@pytest.fixture
def captured(eldercare_logger: logging.Logger) -> io.StringIO:
    """Capture JSON log lines into an in-memory stream."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    eldercare_logger.addHandler(handler)
    yield stream
    eldercare_logger.removeHandler(handler)
    handler.close()


def _records(stream: io.StringIO) -> list[dict]:
    text = stream.getvalue().strip()
    assert text, "expected at least one JSON log line"
    return [json.loads(line) for line in text.splitlines()]


def _assert_no_raw_secrets(blob: str) -> None:
    assert _DUMMY_USER not in blob
    assert _DUMMY_PASS not in blob
    assert _DUMMY_TOKEN not in blob


def test_emitted_line_parses_as_json_with_stable_keys(captured: io.StringIO) -> None:
    get_logger("vision", component="capture").info("stream started")
    (record,) = _records(captured)
    # Exact key set: no camera_id/incident_id/error when unbound.
    assert set(record) == _STABLE_KEYS


@pytest.mark.parametrize(
    ("call_level", "expected"),
    [("info", "INFO"), ("warning", "WARNING"), ("error", "ERROR")],
)
def test_timestamp_utc_z_and_level_matches(
    captured: io.StringIO, call_level: str, expected: str
) -> None:
    getattr(get_logger("vision"), call_level)("hello")
    (record,) = _records(captured)
    timestamp = record["timestamp"]
    assert timestamp.endswith("Z")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert record["level"] == expected


def test_bound_fields_appear_on_every_record(captured: io.StringIO) -> None:
    logger = get_logger("vision", component="capture", camera_id="cam-01", incident_id="inc-42")
    logger.info("first")
    logger.warning("second")
    first, second = _records(captured)
    for record in (first, second):
        assert record["service"] == "vision"
        assert record["component"] == "capture"
        assert record["camera_id"] == "cam-01"
        assert record["incident_id"] == "inc-42"


def test_unbound_component_is_null_and_ids_absent(captured: io.StringIO) -> None:
    get_logger("api").info("ping")
    (record,) = _records(captured)
    assert record["component"] is None
    assert "camera_id" not in record
    assert "incident_id" not in record


def test_non_string_bound_values_stringified(captured: io.StringIO) -> None:
    get_logger("vision", camera_id=7).info("ping")
    (record,) = _records(captured)
    assert record["camera_id"] == "7"


def test_event_defaults_and_overrides_via_extra(captured: io.StringIO) -> None:
    logger = get_logger("vision", component="capture")
    logger.info("plain")
    logger.info("state change", extra={"event": "camera.online"})
    plain, coded = _records(captured)
    assert plain["event"] == "event.unspecified"
    assert coded["event"] == "camera.online"


def test_debug_suppressed_at_info_shown_at_debug(
    captured: io.StringIO, eldercare_logger: logging.Logger
) -> None:
    logger = get_logger("vision")
    logger.debug("hidden")
    assert captured.getvalue() == ""
    configure_logging("DEBUG")
    assert eldercare_logger.level == logging.DEBUG
    logger.debug("visible")
    (record,) = _records(captured)
    assert record["level"] == "DEBUG"
    assert record["message"] == "visible"


@pytest.mark.parametrize("bad_level", ["VERBOSE", "TRACE", "", "INFO2", None, 123])
def test_invalid_level_raises_valueerror_naming_value(
    eldercare_logger: logging.Logger, bad_level: object
) -> None:
    with pytest.raises(ValueError) as exc_info:
        configure_logging(bad_level)  # type: ignore[arg-type]
    assert str(bad_level) in str(exc_info.value)
    assert eldercare_logger.level == logging.INFO


def test_configure_logging_idempotent_single_handler_no_duplicate_lines(
    eldercare_logger: logging.Logger,
) -> None:
    configure_logging("INFO")
    configure_logging("INFO")
    configure_logging("INFO")
    managed = [
        handler
        for handler in eldercare_logger.handlers
        if isinstance(handler, logging.StreamHandler)
    ]
    assert len(managed) == 1
    (handler,) = managed
    buffer = io.StringIO()
    previous = handler.setStream(buffer)
    try:
        get_logger("vision").info("once")
    finally:
        handler.setStream(previous)
    lines = [line for line in buffer.getvalue().strip().splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "once"


def test_adversarial_secrets_sanitized_on_all_paths(captured: io.StringIO) -> None:
    logger = get_logger("vision", component="capture", camera_id="cam-01")
    logger.info(f"message path url={_RTSP_WITH_CREDS} password={_DUMMY_PASS}")
    logger.info("args path url=%s token=%s", _RTSP_WITH_CREDS, f"token={_DUMMY_TOKEN}")
    logger.info(
        "extra path",
        extra={
            "stream_url": _RTSP_WITH_CREDS,
            "auth_token": _DUMMY_TOKEN,
            "db": _PG_WITH_CREDS,
        },
    )
    try:
        raise ConnectionError(f"cannot reach {_RTSP_WITH_CREDS}: timeout")
    except ConnectionError:
        logger.exception("exception path")
    blob = captured.getvalue()
    assert blob.count("\n") >= 4
    _assert_no_raw_secrets(blob)
    assert "camera01.local" in blob  # host context preserved for debugging


@pytest.mark.parametrize(
    "adversarial",
    ["a/b", "a?b", "a#b", "a b"],
    ids=["slash", "question", "hash", "space"],
)
def test_adversarial_password_shapes_no_leak(captured: io.StringIO, adversarial: str) -> None:
    url = f"rtsp://{_DUMMY_USER}:{adversarial}@camera01.local:554/stream1"
    get_logger("vision").info("open %s", url)
    blob = captured.getvalue()
    assert adversarial not in blob
    assert _DUMMY_USER not in blob
    assert "camera01.local" in blob


def test_exc_info_renders_sanitized_error(captured: io.StringIO) -> None:
    try:
        raise ConnectionError(f"cannot reach {_RTSP_WITH_CREDS}")
    except ConnectionError:
        get_logger("vision").exception("stream failed")
    (record,) = _records(captured)
    assert record["message"] == "stream failed"
    assert set(record) <= _STABLE_KEYS | _OPTIONAL_KEYS
    error = record["error"]
    assert error["type"] == "ConnectionError"
    assert _DUMMY_PASS not in error["message"]
    assert _DUMMY_USER not in error["message"]
    assert "camera01.local" in error["message"]
    blob = captured.getvalue()
    assert "Traceback" not in blob
    _assert_no_raw_secrets(blob)


def test_sensitive_bound_key_masked(captured: io.StringIO) -> None:
    get_logger("api", api_token=_DUMMY_TOKEN).info("ping")
    (record,) = _records(captured)
    assert record["extra"]["api_token"] == "***"
    _assert_no_raw_secrets(captured.getvalue())
