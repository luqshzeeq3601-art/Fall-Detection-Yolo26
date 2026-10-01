"""Typed configuration boundary for ElderCare Vision (P0-005).

Loads settings from process environment (and an optional local ``.env``
file) with fail-closed validation. No service integrations live here —
this module only defines the boundary.

``DATABASE_URL`` precedence (documented, tested): an explicitly supplied
(non-empty) ``DATABASE_URL`` wins; otherwise it is composed from the
``POSTGRES_*`` parts as
``postgresql://<user>:<password>@postgres:5432/<db>`` (mirroring
``docker-compose.yml``).
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_POSTGRES_SCHEMES = frozenset({"postgresql", "postgres"})


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    POSTGRES_USER: str = Field(min_length=1)
    POSTGRES_PASSWORD: str = Field(min_length=1)
    POSTGRES_DB: str = Field(min_length=1)
    DATABASE_URL: str | None = Field(default=None)
    MQTT_HOST: str = Field(default="mosquitto", min_length=1)
    MQTT_PORT: int = Field(default=1883, ge=1, le=65535)
    MQTT_SITE_ID: str = Field(default="local-site", min_length=1)
    LOG_LEVEL: LogLevel = "INFO"
    RTSP_URL: str = ""
    VLM_API_KEY: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        try:
            parts = urlsplit(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("DATABASE_URL must be a valid postgresql:// URL") from exc
        if parts.scheme not in _POSTGRES_SCHEMES or not parts.hostname:
            raise ValueError("DATABASE_URL must be a valid postgresql:// URL with host")
        return value

    @field_validator("RTSP_URL")
    @classmethod
    def _validate_rtsp_url(cls, value: str) -> str:
        if value == "":
            return value
        try:
            parts = urlsplit(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("RTSP_URL must be a valid URL") from exc
        if not parts.scheme or not parts.hostname:
            raise ValueError("RTSP_URL must be a valid URL with scheme and host")
        try:
            _port = parts.port
        except ValueError as exc:
            raise ValueError("RTSP_URL must be a valid URL with numeric port") from exc
        return value

    @property
    def database_url(self) -> str:
        """Return the effective database URL.

        A directly supplied ``DATABASE_URL`` wins when set; otherwise the
        URL is composed from the ``POSTGRES_*`` parts.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@postgres:5432/{self.POSTGRES_DB}"
        )

    def redacted_summary(self) -> dict:
        """Return all fields with secrets redacted for safe logging."""
        from eldercare.common.redaction import (
            redact_database_url,
            redact_mapping,
            redact_rtsp_url,
        )

        summary = {
            "POSTGRES_USER": self.POSTGRES_USER,
            "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
            "POSTGRES_DB": self.POSTGRES_DB,
            "DATABASE_URL": self.database_url,
            "MQTT_HOST": self.MQTT_HOST,
            "MQTT_PORT": self.MQTT_PORT,
            "MQTT_SITE_ID": self.MQTT_SITE_ID,
            "LOG_LEVEL": self.LOG_LEVEL,
            "RTSP_URL": self.RTSP_URL,
            "VLM_API_KEY": self.VLM_API_KEY,
        }
        redacted = redact_mapping(summary, {"POSTGRES_PASSWORD", "VLM_API_KEY"})
        redacted["DATABASE_URL"] = redact_database_url(self.database_url)
        redacted["RTSP_URL"] = redact_rtsp_url(self.RTSP_URL)
        return redacted
