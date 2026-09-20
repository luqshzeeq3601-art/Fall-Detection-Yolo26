"""Unit tests for the CameraConfig boundary (P1-001).

TDD RED-first suite covering the eight brief areas. Every credential value
below is a dummy placeholder used in-process only; nothing is written to disk.
"""

from __future__ import annotations

import io
import logging

import pytest
from pydantic import ValidationError

from eldercare.common.logger import JsonFormatter, configure_logging, get_logger
from eldercare.common.redaction import UNPARSEABLE_URL_SENTINEL, redact_rtsp_url
from eldercare.vision.stream.camera import CameraConfig, ensure_unique_camera_ids

_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_RTSP_PLAIN = "rtsp://camera01.local:554/stream1"
_RTSP_RTSPS = "rtsps://camera01.local:322/stream1"
_RTSP_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"


def _assert_no_raw_secrets(blob: str) -> None:
    assert _DUMMY_USER not in blob
    assert _DUMMY_PASS not in blob


# --- Area 1: valid configs -------------------------------------------------


def test_valid_minimal_no_credentials() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_PLAIN)
    assert cfg.camera_id == "cam-01"
    assert cfg.name == "Lobby"
    assert cfg.enabled is True
    assert cfg.rtsp_url == _RTSP_PLAIN
    assert cfg.location is None
    assert cfg.description is None


def test_valid_rtsps_scheme_accepted() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_RTSPS)
    assert cfg.rtsp_url == _RTSP_RTSPS


def test_valid_credentialed_url_accepted() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    assert cfg.rtsp_url == _RTSP_CREDS


def test_valid_disabled_config() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", enabled=False, rtsp_url=_RTSP_PLAIN)
    assert cfg.enabled is False


def test_valid_with_metadata_stored_inert() -> None:
    cfg = CameraConfig(
        camera_id="cam-01",
        name="Lobby",
        rtsp_url=_RTSP_PLAIN,
        location="Floor 1 lobby",
        description="Ceiling-mounted hallway camera",
    )
    assert cfg.location == "Floor 1 lobby"
    assert cfg.description == "Ceiling-mounted hallway camera"


def test_model_is_frozen() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_PLAIN)
    with pytest.raises(ValidationError):
        cfg.name = "Other"  # type: ignore[misc]


# --- Area 2: malformed rtsp_url --------------------------------------------


@pytest.mark.parametrize(
    ("bad_url", "case"),
    [
        ("camera01.local:554/stream1", "missing-scheme"),
        ("http://camera01.local/stream1", "wrong-scheme"),
        ("https://camera01.local/stream1", "wrong-scheme-https"),
        ("rtsp:///stream1", "missing-host"),
        ("rtsp://camera01.local:badport/stream1", "non-numeric-port"),
        ("", "empty-rejected"),
    ],
)
def test_malformed_rtsp_url_rejected(bad_url: str, case: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=bad_url)
    assert "rtsp_url" in str(exc_info.value), case


def test_malformed_credentialed_url_error_is_password_free() -> None:
    bad = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:badport/stream1"
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=bad)
    _assert_no_raw_secrets(str(exc_info.value))


def test_rtsp_validator_messages_never_embed_input() -> None:
    marker = "leak-marker-xyz-host"
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=f"http://{marker}/s")
    assert marker not in str(exc_info.value)


# --- Area 3: missing required fields ----------------------------------------


@pytest.mark.parametrize("missing", ["camera_id", "name", "rtsp_url"])
def test_missing_each_required_field_raises_naming_field(missing: str) -> None:
    kwargs = {"camera_id": "cam-01", "name": "Lobby", "rtsp_url": _RTSP_PLAIN}
    del kwargs[missing]
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(**kwargs)  # type: ignore[arg-type]
    assert missing in str(exc_info.value)


# --- Area 4: identity rules --------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["cam 01", "cam/01", "cam@01", "cam.01", "cam:01", "cam+01", ""],
    ids=["space", "slash", "at", "dot", "colon", "plus", "empty"],
)
def test_illegal_camera_id_chars_rejected(bad_id: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id=bad_id, name="Lobby", rtsp_url=_RTSP_PLAIN)
    assert "camera_id" in str(exc_info.value)


def test_overlong_camera_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="c" * 65, name="Lobby", rtsp_url=_RTSP_PLAIN)
    assert "camera_id" in str(exc_info.value)


def test_overlong_name_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="n" * 129, rtsp_url=_RTSP_PLAIN)
    assert "name" in str(exc_info.value)


@pytest.mark.parametrize("blank", ["   ", "\t\n ", "\u2003"])
def test_whitespace_only_name_rejected(blank: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name=blank, rtsp_url=_RTSP_PLAIN)
    assert "name" in str(exc_info.value)


def test_name_surrounding_whitespace_stripped() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="  Lobby  ", rtsp_url=_RTSP_PLAIN)
    assert cfg.name == "Lobby"


@pytest.mark.parametrize("bad_enabled", ["true", "yes", "1", 1, 0, None, 1.0])
def test_non_bool_enabled_rejected(bad_enabled: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", enabled=bad_enabled, rtsp_url=_RTSP_PLAIN)  # type: ignore[arg-type]
    assert "enabled" in str(exc_info.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("location", "l" * 129),
        ("description", "d" * 513),
    ],
)
def test_overlong_metadata_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_PLAIN, **{field: value})  # type: ignore[arg-type]
    assert field in str(exc_info.value)


# --- Area 5: credential redaction on every path ------------------------------


def test_repr_redacts_credentials() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    blob = repr(cfg)
    _assert_no_raw_secrets(blob)
    assert "camera01.local" in blob


def test_str_redacts_credentials() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    blob = str(cfg)
    _assert_no_raw_secrets(blob)
    assert "camera01.local" in blob


def test_rich_repr_redacts_credentials() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    pairs = list(cfg.__rich_repr__())
    blob = str(pairs)
    _assert_no_raw_secrets(blob)
    assert "camera01.local" in blob
    assert ("rtsp_url", redact_rtsp_url(_RTSP_CREDS)) in pairs


def test_rich_repr_and_repr_stay_redacted_together() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    _assert_no_raw_secrets(str(list(cfg.__rich_repr__())))
    _assert_no_raw_secrets(repr(cfg))
    assert "camera01.local" in repr(cfg)


def test_model_dump_safe_redacts_credentials() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    safe = cfg.model_dump_safe()
    assert safe["rtsp_url"] == redact_rtsp_url(_RTSP_CREDS)
    _assert_no_raw_secrets(str(safe))
    assert "camera01.local" in safe["rtsp_url"]
    assert "@" not in safe["rtsp_url"]


def test_credentialed_url_redacted_in_logger_json_line() -> None:
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
        cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
        get_logger("vision", component="capture").info("opening %s", cfg)
        safe = cfg.model_dump_safe()
        get_logger("vision", component="capture").info("repr=%r safe=%s", cfg, safe)
    finally:
        logger.removeHandler(handler)
        handler.close()
        for saved in saved_handlers:
            logger.addHandler(saved)
        logger.setLevel(saved_level)
    blob = stream.getvalue()
    assert blob, "expected JSON log lines"
    _assert_no_raw_secrets(blob)
    assert "camera01.local" in blob


def test_nearby_field_failure_hides_credentialed_url() -> None:
    """Behavioral proof of `hide_input_in_errors`: a bad `camera_id` next to
    a credentialed URL must not echo the password in `str(exc)`."""
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="bad id!!", name="Lobby", rtsp_url=_RTSP_CREDS)
    text = str(exc_info.value)
    assert "camera_id" in text
    _assert_no_raw_secrets(text)


# --- Area 6: non-string / adversarial values ----------------------------------


@pytest.mark.parametrize("bad", [None, 123, ["cam-01"], {"id": "cam-01"}])
def test_non_string_camera_id_rejected(bad: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id=bad, name="Lobby", rtsp_url=_RTSP_PLAIN)  # type: ignore[arg-type]
    assert "camera_id" in str(exc_info.value)


@pytest.mark.parametrize("bad", [None, 123, ["Lobby"], {"name": "Lobby"}])
def test_non_string_name_rejected(bad: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name=bad, rtsp_url=_RTSP_PLAIN)  # type: ignore[arg-type]
    assert "name" in str(exc_info.value)


@pytest.mark.parametrize("bad", [None, 123, [_RTSP_PLAIN], {"url": _RTSP_PLAIN}])
def test_non_string_rtsp_url_rejected(bad: object) -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=bad)  # type: ignore[arg-type]
    assert "rtsp_url" in str(exc_info.value)


def test_extremely_long_camera_id_rejected_without_crash() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="c" * 10_000, name="Lobby", rtsp_url=_RTSP_PLAIN)
    assert "camera_id" in str(exc_info.value)


def test_extremely_long_rtsp_url_never_leaks() -> None:
    long_url = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/" + "s" * 10_000
    try:
        cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=long_url)
    except ValidationError as exc:
        _assert_no_raw_secrets(str(exc))
    else:
        _assert_no_raw_secrets(repr(cfg))
        _assert_no_raw_secrets(str(cfg.model_dump_safe()))


def test_unicode_name_accepted() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Cámara 日本語 🎥", rtsp_url=_RTSP_PLAIN)
    assert "Cámara" in cfg.name


def test_unicode_camera_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CameraConfig(camera_id="cam-é01", name="Lobby", rtsp_url=_RTSP_PLAIN)
    assert "camera_id" in str(exc_info.value)


def test_adversarial_password_shape_never_leaks() -> None:
    raw = f"rtsp://{_DUMMY_USER}:p@ss/w?x#y z@host/stream"
    try:
        cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=raw)
    except ValidationError as exc:
        _assert_no_raw_secrets(str(exc))
        assert raw not in str(exc)
    else:
        _assert_no_raw_secrets(repr(cfg))
        _assert_no_raw_secrets(str(cfg))
        _assert_no_raw_secrets(str(cfg.model_dump_safe()))


# --- Area 7: uniqueness helper -------------------------------------------------


def test_duplicate_camera_ids_rejected_naming_id_without_leak() -> None:
    first = CameraConfig(camera_id="cam-01", name="A", rtsp_url=_RTSP_CREDS)
    second = CameraConfig(camera_id="cam-01", name="B", rtsp_url=_RTSP_CREDS)
    with pytest.raises(ValueError) as exc_info:
        ensure_unique_camera_ids([first, second])
    assert "cam-01" in str(exc_info.value)
    _assert_no_raw_secrets(str(exc_info.value))


def test_empty_and_unique_configs_pass() -> None:
    assert ensure_unique_camera_ids([]) is None
    configs = [
        CameraConfig(camera_id="cam-01", name="A", rtsp_url=_RTSP_PLAIN),
        CameraConfig(camera_id="cam-02", name="B", rtsp_url=_RTSP_PLAIN),
    ]
    assert ensure_unique_camera_ids(configs) is None
    assert ensure_unique_camera_ids(tuple(configs)) is None


# --- Area 8: raw vs safe dumps --------------------------------------------------


def test_model_dump_raw_keeps_real_url_while_safe_does_not() -> None:
    cfg = CameraConfig(camera_id="cam-01", name="Lobby", rtsp_url=_RTSP_CREDS)
    raw = cfg.model_dump()
    safe = cfg.model_dump_safe()
    assert raw["rtsp_url"] == _RTSP_CREDS
    assert safe["rtsp_url"] == redact_rtsp_url(_RTSP_CREDS)
    assert safe["rtsp_url"] != _RTSP_CREDS
    assert isinstance(UNPARSEABLE_URL_SENTINEL, str) and UNPARSEABLE_URL_SENTINEL
    for key in ("camera_id", "name", "enabled", "location", "description"):
        assert safe[key] == raw[key]
