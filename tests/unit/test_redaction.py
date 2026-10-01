"""Unit tests for secret-redaction helpers (P0-005).

Pure-stdlib helpers in ``eldercare.common.redaction``. All credential
values below are dummy placeholders used in-process only.
"""

import pytest

from eldercare.common.redaction import (
    UNPARSEABLE_URL_SENTINEL,
    redact_database_url,
    redact_mapping,
    redact_rtsp_url,
    redact_token,
    sanitize_exception_message,
)

_DUMMY_USER = "dummyuser"
_DUMMY_PASS = "dummy-pass-123"
_RTSP_WITH_CREDS = f"rtsp://{_DUMMY_USER}:{_DUMMY_PASS}@camera01.local:554/stream1"
_PG_WITH_CREDS = f"postgresql://{_DUMMY_USER}:{_DUMMY_PASS}@postgres:5432/eldercare_dummy"


def test_redact_rtsp_url_strips_userinfo_keeps_rest() -> None:
    redacted = redact_rtsp_url(_RTSP_WITH_CREDS)
    assert _DUMMY_USER not in redacted
    assert _DUMMY_PASS not in redacted
    assert "camera01.local" in redacted
    assert "554" in redacted
    assert "/stream1" in redacted
    assert redacted.startswith("rtsp://")
    assert "@" not in redacted


@pytest.mark.parametrize(
    "bad_input",
    ["not-a-url", "://missing-scheme", "http://[::1", "///no-host-here", 12345],
)
def test_redact_rtsp_url_unparseable_returns_sentinel(bad_input: object) -> None:
    redacted = redact_rtsp_url(bad_input)  # type: ignore[arg-type]
    assert redacted == UNPARSEABLE_URL_SENTINEL
    if isinstance(bad_input, str):
        assert bad_input not in redacted or bad_input == redacted


def test_redact_rtsp_url_without_userinfo_is_stable() -> None:
    plain = "rtsp://camera01.local:554/stream1"
    assert redact_rtsp_url(plain) == plain


def test_redact_database_url_strips_password_preserves_host_db() -> None:
    redacted = redact_database_url(_PG_WITH_CREDS)
    assert _DUMMY_PASS not in redacted
    assert _DUMMY_USER not in redacted
    assert "postgres" in redacted
    assert "5432" in redacted
    assert "eldercare_dummy" in redacted
    assert redacted.startswith("postgresql://")
    assert "@" not in redacted


def test_redact_database_url_unparseable_returns_sentinel() -> None:
    assert redact_database_url("definitely-not-a-url") == UNPARSEABLE_URL_SENTINEL


def test_redact_token_long_value_shows_first2_last2_only() -> None:
    assert redact_token("abcdefgh") == "ab***gh"
    assert redact_token("dummy-token-value-xyz") == "du***yz"


@pytest.mark.parametrize(
    "short_value", ["", "a", "abc", "1234567", None], ids=["empty", "1ch", "3ch", "7ch", "none"]
)
def test_redact_token_short_or_empty_returns_full_mask(short_value: object) -> None:
    assert redact_token(short_value) == "***"  # type: ignore[arg-type]


def test_redact_mapping_case_insensitive_default_keys() -> None:
    data = {
        "POSTGRES_PASSWORD": _DUMMY_PASS,
        "Db_Passwd": _DUMMY_PASS,
        "VLM_API_KEY": "dummy-key",
        "AuthToken": "dummy-token",
        "apiSecret": "dummy-secret",
        "username": _DUMMY_USER,
        "MQTT_HOST": "mosquitto",
        "MQTT_PORT": 1883,
    }
    redacted = redact_mapping(data)
    for key in (
        "POSTGRES_PASSWORD",
        "Db_Passwd",
        "VLM_API_KEY",
        "AuthToken",
        "apiSecret",
    ):
        assert redacted[key] == "***"
    assert redacted["username"] == _DUMMY_USER
    assert redacted["MQTT_HOST"] == "mosquitto"
    assert redacted["MQTT_PORT"] == 1883


def test_redact_mapping_caller_supplied_key_set() -> None:
    data = {"custom_secret": "s3cr3t", "POSTGRES_PASSWORD": _DUMMY_PASS, "host": "x"}
    redacted = redact_mapping(data, {"CUSTOM_SECRET"})
    assert redacted["custom_secret"] == "***"
    # Caller-supplied set replaces the default matching: other keys untouched.
    assert redacted["POSTGRES_PASSWORD"] == _DUMMY_PASS
    assert redacted["host"] == "x"


def test_redact_mapping_does_not_mutate_input() -> None:
    data = {"api_key": "dummy"}
    redact_mapping(data)
    assert data == {"api_key": "dummy"}


def test_sanitize_exception_message_removes_url_password() -> None:
    try:
        raise ConnectionError(f"cannot reach {_RTSP_WITH_CREDS}: timeout")
    except ConnectionError as exc:
        cleaned = sanitize_exception_message(str(exc))
    assert _DUMMY_PASS not in cleaned
    assert _DUMMY_USER not in cleaned
    assert "camera01.local" in cleaned  # host context preserved for debugging


def test_sanitize_exception_message_removes_key_value_secrets() -> None:
    msg = "auth failed: password=dummy-pass-123 token=abcdef123456 for user dummyuser"
    cleaned = sanitize_exception_message(msg)
    assert "dummy-pass-123" not in cleaned
    assert "abcdef123456" not in cleaned
    assert "dummyuser" in cleaned


def test_sanitize_formatted_log_line_with_credentialed_url() -> None:
    log_line = (
        f"ERROR eldercare.vision: stream open failed url={_RTSP_WITH_CREDS} "
        f"db={_PG_WITH_CREDS} retry=3"
    )
    cleaned = sanitize_exception_message(log_line)
    assert _DUMMY_PASS not in cleaned
    assert _DUMMY_USER not in cleaned
    assert "retry=3" in cleaned


@pytest.mark.parametrize(
    "adversarial_password",
    ["a/b", "a?b", "a#b", "a b", "p@ss:w/d?x#y z"],
    ids=["slash", "question", "hash", "space", "all-specials"],
)
def test_sanitize_exception_message_adversarial_passwords_no_leak(
    adversarial_password: str,
) -> None:
    msg = f"err url=rtsp://{_DUMMY_USER}:{adversarial_password}@camera01.local:554/stream1 end"
    cleaned = sanitize_exception_message(msg)
    assert adversarial_password not in cleaned
    assert _DUMMY_USER not in cleaned
    assert "camera01.local" in cleaned


def test_redact_mapping_non_string_keys_no_throw() -> None:
    data = {
        1: "int-key-value",
        None: "none-key-value",
        ("tuple", "key"): "tuple-key-value",
        "password": _DUMMY_PASS,
        "username": _DUMMY_USER,
    }
    redacted = redact_mapping(data)  # type: ignore[dict-item]
    assert redacted[1] == "int-key-value"
    assert redacted[None] == "none-key-value"
    assert redacted[("tuple", "key")] == "tuple-key-value"
    assert redacted["password"] == "***"
    assert redacted["username"] == _DUMMY_USER
