"""Secret-redaction helpers for logs, exceptions, and summaries.

Pure standard library. Every function is fail-closed: on any failure path
the raw input is never returned — a fixed sentinel or full mask is used
instead so credentials cannot leak into logs or error text.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

#: Returned when a URL cannot be parsed instead of echoing the raw input.
UNPARSEABLE_URL_SENTINEL = "<unparseable-url>"

#: Full mask used for tokens, passwords, and mapping values.
FULL_MASK = "***"

_DEFAULT_SENSITIVE_PATTERN = re.compile(
    r"password|passwd|secret|token|api_?key|auth", re.IGNORECASE
)
_SCHEME_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://")
_STRICT_HOST_TOKEN_PATTERN = re.compile(r"^(?:\[[^\s\]]+\]|[\w.\-]+)(:\d+)?([/?#][^\s]*)?$")
_PERMISSIVE_HOST_TOKEN_PATTERN = re.compile(
    r"^(?:\[[^\s\]]+\]|[\w.\-]+)(:[^\s/?#]*)?([/?#][^\s]*)?$"
)
_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api_?key)\s*([=:])\s*(\S+)"
)


def _redact_urls_in_text(message: str) -> str:
    """Replace userinfo in every URL-looking substring with ``***``.

    For each ``scheme://`` occurrence, the userinfo is taken to run up to
    the last ``@`` whose trailing token (up to whitespace) looks like a
    host. This spans passwords containing ``/``, ``?``, ``#``, ``@``,
    and spaces, so no password characters survive. The search window ends
    at the next ``scheme://`` (or end of text) to avoid merging separate
    URLs. Matching prefers strict host tokens (numeric port) and falls
    back to permissive ones, then to the last ``@`` fail-closed.
    """
    matches = list(_SCHEME_PATTERN.finditer(message))
    if not matches:
        return message
    chosen: list[tuple[int, int]] = []
    for index, match in enumerate(matches):
        userinfo_start = match.end()
        window_end = matches[index + 1].start() if index + 1 < len(matches) else len(message)
        if userinfo_start >= window_end:
            continue
        segment = message[userinfo_start:window_end]
        at_offsets = [i for i, ch in enumerate(segment) if ch == "@"]
        if not at_offsets:
            continue
        strict: list[int] = []
        permissive: list[int] = []
        for offset in at_offsets:
            at = userinfo_start + offset
            after = message[at + 1 : window_end]
            if not after or after[0].isspace():
                continue
            token = after.split(None, 1)[0]
            if "@" in token:
                continue
            if _STRICT_HOST_TOKEN_PATTERN.match(token):
                strict.append(at)
            elif _PERMISSIVE_HOST_TOKEN_PATTERN.match(token):
                permissive.append(at)
        if strict:
            chosen.append((userinfo_start, strict[-1]))
        elif permissive:
            chosen.append((userinfo_start, permissive[-1]))
        else:
            chosen.append((userinfo_start, userinfo_start + at_offsets[-1]))
    cleaned = message
    for start, at in sorted(chosen, reverse=True):
        cleaned = cleaned[:start] + FULL_MASK + cleaned[at:]
    return cleaned


def _strip_userinfo(url: object) -> str:
    """Return *url* with any ``user:password@`` userinfo removed."""
    if not isinstance(url, str):
        return UNPARSEABLE_URL_SENTINEL
    if url == "":
        return ""
    try:
        parts = urlsplit(url)
    except (ValueError, AttributeError, TypeError):
        return UNPARSEABLE_URL_SENTINEL
    if not parts.scheme or not parts.netloc:
        return UNPARSEABLE_URL_SENTINEL
    host = parts.hostname
    if not host:
        return UNPARSEABLE_URL_SENTINEL
    try:
        port = parts.port
    except ValueError:
        return UNPARSEABLE_URL_SENTINEL
    netloc = host if port is None else f"{host}:{port}"
    try:
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except (ValueError, AttributeError, TypeError):
        return UNPARSEABLE_URL_SENTINEL


def redact_rtsp_url(url: object) -> str:
    """Strip ``user:password@`` userinfo from an RTSP URL.

    Scheme, host, port, and path are preserved. Unparseable input yields
    :data:`UNPARSEABLE_URL_SENTINEL` — never the raw input. An empty
    string (disabled stream) passes through unchanged.
    """
    return _strip_userinfo(url)


def redact_database_url(url: object) -> str:
    """Strip ``user:password@`` userinfo from a ``postgresql://`` URL.

    Host, port, and database name are preserved. Unparseable input yields
    :data:`UNPARSEABLE_URL_SENTINEL` — never the raw input. An empty
    string passes through unchanged.
    """
    return _strip_userinfo(url)


def redact_token(value: object) -> str:
    """Redact a token/API key.

    Values of length >= 8 show first 2 + ``***`` + last 2 characters;
    shorter values, empty strings, and ``None`` return the full mask.
    """
    if not isinstance(value, str) or len(value) < 8:
        return FULL_MASK
    return f"{value[:2]}***{value[-2:]}"


def redact_mapping(data: Mapping[str, Any], sensitive_keys: set[str] | None = None) -> dict:
    """Return a copy of *data* with sensitive values replaced by ``***``.

    When *sensitive_keys* is ``None``, a key is sensitive if it matches
    ``password|passwd|secret|token|api_key|apikey|auth`` (case-insensitive
    substring match). When a caller-supplied set is given, keys matching
    it exactly (case-insensitive) are redacted instead.
    """
    redacted: dict = {}
    if sensitive_keys is None:
        for key, value in data.items():
            if isinstance(key, str) and _DEFAULT_SENSITIVE_PATTERN.search(key):
                redacted[key] = FULL_MASK
            else:
                redacted[key] = value
        return redacted
    lowered = {str(key).lower() for key in sensitive_keys}
    for key, value in data.items():
        if str(key).lower() in lowered:
            redacted[key] = FULL_MASK
        else:
            redacted[key] = value
    return redacted


def sanitize_exception_message(message: object) -> str:
    """Redact credentials from arbitrary error/log text.

    Strips userinfo from embedded URLs and masks ``key=value``/``key: value``
    secrets so exceptions and log lines never leak credentials. Non-string
    input yields the full mask rather than an echo of the input.
    """
    if not isinstance(message, str):
        return FULL_MASK
    cleaned = _redact_urls_in_text(message)
    cleaned = _KEY_VALUE_SECRET_PATTERN.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{FULL_MASK}", cleaned
    )
    return cleaned
