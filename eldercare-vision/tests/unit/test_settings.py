"""Unit tests for the typed Settings boundary (P0-005).

All credential values below are dummy placeholders applied to the
process environment via monkeypatch only; nothing is written to disk.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from eldercare.common.settings import Settings

REQUIRED_VARS = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
MANAGED_ENV_VARS = REQUIRED_VARS + (
    "DATABASE_URL",
    "MQTT_HOST",
    "MQTT_PORT",
    "LOG_LEVEL",
    "RTSP_URL",
    "VLM_API_KEY",
)

_DUMMY_REQUIRED = {
    "POSTGRES_USER": "dummy-user",
    "POSTGRES_PASSWORD": "dummy-pass-123",
    "POSTGRES_DB": "dummy_db",
}


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in MANAGED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _load_with_required(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    env = dict(_DUMMY_REQUIRED)
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


@pytest.mark.parametrize("missing", REQUIRED_VARS)
def test_missing_each_required_var_raises_naming_field(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for key, value in _DUMMY_REQUIRED.items():
        if key != missing:
            monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert missing in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_port",
    ["not-a-number", "0", "99999", "-1", "3.5"],
    ids=["alpha", "zero", "huge", "neg", "float"],
)
def test_malformed_mqtt_port_raises(monkeypatch: pytest.MonkeyPatch, bad_port: str) -> None:
    with pytest.raises(ValidationError):
        _load_with_required(monkeypatch, MQTT_PORT=bad_port)


def test_malformed_rtsp_url_raises_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _load_with_required(monkeypatch, RTSP_URL="not-a-url")


def test_empty_rtsp_url_means_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_with_required(monkeypatch, RTSP_URL="")
    assert settings.RTSP_URL == ""


def test_valid_rtsp_url_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_with_required(
        monkeypatch, RTSP_URL="rtsp://dummyuser:dummy-pass-123@cam.local:554/s"
    )
    assert settings.RTSP_URL.startswith("rtsp://")


def test_database_url_direct_value_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    direct = "postgresql://direct-user:direct-pass-xyz@dbhost:5432/directdb"
    settings = _load_with_required(monkeypatch, DATABASE_URL=direct)
    assert settings.database_url == direct


def test_database_url_composed_from_parts_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_with_required(monkeypatch)
    assert settings.database_url == (
        "postgresql://dummy-user:dummy-pass-123@postgres:5432/dummy_db"
    )


def test_database_url_empty_string_falls_back_to_composed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_with_required(monkeypatch, DATABASE_URL="")
    assert settings.database_url == (
        "postgresql://dummy-user:dummy-pass-123@postgres:5432/dummy_db"
    )


def test_malformed_database_url_raises_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _load_with_required(monkeypatch, DATABASE_URL="not-a-url")


def test_safe_defaults_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_with_required(monkeypatch)
    assert settings.MQTT_HOST == "mosquitto"
    assert settings.MQTT_PORT == 1883
    assert settings.LOG_LEVEL == "INFO"
    assert settings.RTSP_URL == ""
    assert settings.VLM_API_KEY == ""


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _load_with_required(monkeypatch, LOG_LEVEL="VERBOSE")


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_valid_log_levels_accepted(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    settings = _load_with_required(monkeypatch, LOG_LEVEL=level)
    assert settings.LOG_LEVEL == level


def test_redacted_summary_never_exposes_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_with_required(
        monkeypatch,
        RTSP_URL="rtsp://dummyuser:dummy-pass-123@cam.local:554/s",
        VLM_API_KEY="dummy-vlm-key-abcdef",
    )
    summary = settings.redacted_summary()
    blob = str(summary)
    assert "dummy-pass-123" not in blob
    assert "dummyuser" not in blob
    assert "dummy-vlm-key-abcdef" not in blob
    assert summary["POSTGRES_PASSWORD"] == "***"
    assert summary["VLM_API_KEY"] == "***"
    assert "cam.local" in summary["RTSP_URL"]
    assert "@" not in summary["RTSP_URL"]
    assert "@" not in summary["DATABASE_URL"]
    assert "postgres" in summary["DATABASE_URL"]
    # Non-sensitive values pass through intact.
    assert summary["POSTGRES_USER"] == "dummy-user"
    assert summary["MQTT_HOST"] == "mosquitto"
    assert summary["MQTT_PORT"] == 1883


def test_env_example_compose_model_reconciliation() -> None:
    """Triple reconciliation: compose POSTGRES_* names exist verbatim in the
    Settings model and in .env.example (parsed in-test, no hardcoded list)."""
    import re

    repo_root = Path(__file__).resolve().parents[2]
    compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    example_text = (repo_root / ".env.example").read_text(encoding="utf-8")

    compose_names = set(re.findall(r"\$\{(POSTGRES_[A-Z_]+)", compose_text))
    assert compose_names, "expected POSTGRES_* references in docker-compose.yml"

    example_names = set(re.findall(r"^([A-Z][A-Z0-9_]*)\s*=", example_text, re.MULTILINE))
    model_names = set(Settings.model_fields.keys())

    for name in compose_names:
        assert name in model_names, f"{name} in compose but missing from Settings model"
        assert name in example_names, f"{name} in compose but missing from .env.example"

    for field in model_names:
        assert field in example_names, f"Settings field {field} missing from .env.example"
