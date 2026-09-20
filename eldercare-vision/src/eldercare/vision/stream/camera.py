"""Typed camera configuration for the RTSP stream manager (P1-001).

Contract (validation boundary only — no streams are opened here):

- ``camera_id: str`` — stable identity, ``min_length=1, max_length=64``,
  pattern ``^[A-Za-z0-9_-]+$`` (safe for topics/paths/URLs). This id is the
  ``camera_id`` key of the frame observation in ``ARCHITECTURE.md`` §5.
- ``name: str`` — human-readable, ``min_length=1, max_length=128``;
  surrounding whitespace is stripped, whitespace-only is rejected.
- ``enabled: StrictBool = True`` — strict bool, no truthy-string coercion.
- ``rtsp_url: str`` — scheme MUST be ``rtsp`` or ``rtsps``, hostname
  required, port numeric when present. Credential-bearing URLs
  (``rtsp://user:pass@host…``) are ACCEPTED (cameras need auth) but the raw
  value never surfaces: ``__repr__``/``__str__``/``model_dump_safe()`` all
  render it via :func:`eldercare.common.redaction.redact_rtsp_url`. Empty
  string is REJECTED (a camera entry with no source is a config error).
- ``location: str | None = None`` (max 128), ``description: str | None =
  None`` (max 512) — future-safe inert metadata; no runtime reads them.

Deliberate differences from P0-005 ``Settings``:

- ``Settings.RTSP_URL`` accepts any ``scheme://host`` URL and empty means
  "disabled" (global default); ``CameraConfig.rtsp_url`` narrows the scheme
  to ``rtsp``/``rtsps`` (this is the RTSP stream manager) and rejects empty
  (a camera entry with no source is a configuration error).
- ``CameraConfig`` is frozen (``frozen=True``); ``Settings`` is mutable.
- Both use ``hide_input_in_errors=True`` so ``str(ValidationError)`` never
  echoes secret input values; all custom validators additionally raise
  generic messages that never embed the input value.

API alignment (``API_SPEC.md`` §3): the future ``GET /cameras`` shape uses
``id``/``name``; this model's ``camera_id`` maps to that ``id``
(``id`` ↔ ``camera_id``). ``model_dump_safe()`` serializes without the
``rtsp_url`` secret per NFR-021 (no FastAPI code in this task).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from eldercare.common.redaction import redact_rtsp_url

_RTSP_SCHEMES = frozenset({"rtsp", "rtsps"})


class CameraConfig(BaseModel):
    """Single camera's validated configuration (frozen, leak-proof)."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    camera_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    enabled: StrictBool = True
    rtsp_url: str
    location: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                raise ValueError("name must not be blank")
            return stripped
        return value

    @field_validator("rtsp_url", mode="before")
    @classmethod
    def _validate_rtsp_url(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("rtsp_url must be a string rtsp(s) URL")
        if value == "":
            raise ValueError("rtsp_url must be a non-empty rtsp(s) URL")
        try:
            parts = urlsplit(value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("rtsp_url must be a valid rtsp(s) URL with host") from exc
        if parts.scheme.lower() not in _RTSP_SCHEMES:
            raise ValueError("rtsp_url must use rtsp or rtsps scheme")
        if not parts.hostname:
            raise ValueError("rtsp_url must be a valid rtsp(s) URL with host")
        try:
            _port = parts.port
        except ValueError as exc:
            raise ValueError("rtsp_url must use a numeric port") from exc
        return value

    def __repr__(self) -> str:
        redacted = redact_rtsp_url(self.rtsp_url)
        return (
            f"CameraConfig(camera_id={self.camera_id!r}, name={self.name!r}, "
            f"enabled={self.enabled!r}, rtsp_url={redacted!r}, "
            f"location={self.location!r}, description={self.description!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def __rich_repr__(self) -> Iterator[tuple[str, Any]]:
        yield "camera_id", self.camera_id
        yield "name", self.name
        yield "enabled", self.enabled
        yield "rtsp_url", redact_rtsp_url(self.rtsp_url)
        yield "location", self.location
        yield "description", self.description

    def model_dump_safe(self) -> dict[str, Any]:
        """Return ``model_dump()`` with ``rtsp_url`` replaced by its redacted form."""
        dumped = self.model_dump()
        dumped["rtsp_url"] = redact_rtsp_url(self.rtsp_url)
        return dumped


def ensure_unique_camera_ids(configs: Sequence[CameraConfig]) -> None:
    """Fail closed on duplicated ``camera_id`` values (validation only).

    Raises ``ValueError`` naming the duplicated id. Performs no logging
    (so URLs can never reach a log line) and holds no runtime state.
    """
    seen: set[str] = set()
    for config in configs:
        if config.camera_id in seen:
            raise ValueError(f"duplicate camera_id: {config.camera_id}")
        seen.add(config.camera_id)
