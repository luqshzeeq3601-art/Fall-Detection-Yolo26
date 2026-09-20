"""Secret-safe structured JSON logging foundation (P0-006).

Stdlib :mod:`logging` only; no new dependencies.

Public API:

- :func:`configure_logging` — attach exactly one JSON ``StreamHandler(stderr)``
  to the ``eldercare`` root logger. Idempotent: repeated calls reconfigure the
  existing handler in place instead of adding duplicates. Accepts a plain
  level string so later phases can pass ``settings.log_level`` directly; this
  module deliberately does NOT import ``settings`` (dependency direction is
  logger <- settings, never the reverse).
- :func:`get_logger` — bind ``service`` (+ optional ``component`` and extra
  string fields such as ``camera_id``) so every record carries them.
- :class:`JsonFormatter` — one JSON object per line with stable keys.

Event-override API (the single documented way to set an event code): pass
``extra={"event": "<dotted.code>"}`` on the individual log call, e.g.
``logger.info("reconnected", extra={"event": "camera.online"})``. A call-site
``extra`` value wins over an adapter-bound default; records without an
override carry ``"event.unspecified"``.

Secret safety is structural: every message, ``%``-style arg, extra/bound
value, and exception text is routed through the P0-005
:func:`~eldercare.common.redaction.sanitize_exception_message` helper (plus
key-name based :func:`~eldercare.common.redaction.redact_mapping` for mapping
values, so a bare secret under a ``token``/``password``-like key can never
reach the stream even without a ``key=value`` shape).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from eldercare.common.redaction import redact_mapping, sanitize_exception_message

#: Root logger every service builds on.
ROOT_LOGGER_NAME = "eldercare"

#: Event code used when a call does not override one via ``extra``.
DEFAULT_EVENT = "event.unspecified"

#: Mirrors the ``LOG_LEVEL`` Literal in settings.py (kept as a local tuple so
#: this module never imports settings).
_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: Marker attribute identifying the single handler owned by configure_logging.
_MANAGED_ATTR = "_eldercare_managed_json_handler"

#: Top-level keys a formatter may emit besides the always-present stable set.
_TOP_LEVEL_OPTIONAL_KEYS = frozenset({"camera_id", "incident_id", "error"})

#: Attributes owned by the logging machinery itself — never copied into ``extra``.
_STANDARD_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "msg",
        "message",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

#: Record attributes promoted to stable top-level JSON keys (not ``extra``).
_STABLE_ATTRS = frozenset({"service", "component", "event", "camera_id", "incident_id"})


def _safe_str(value: object) -> str:
    """Stringify *value* without ever raising; failure yields a full mask."""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return "***"


class BoundLogger(logging.LoggerAdapter):
    """Adapter that merges call-site ``extra`` over the bound fields.

    The stdlib :meth:`LoggerAdapter.process` overwrites a call's ``extra``
    mapping with the adapter's own, which would silently drop a per-call
    ``extra={"event": ...}`` override. This subclass merges instead, with
    call-site keys winning, so bound ``service``/``component``/``camera_id``
    defaults stay while individual calls can still set ``event``.
    """

    def process(self, msg: object, kwargs: dict[str, Any]) -> tuple[object, dict[str, Any]]:
        merged: dict[str, Any] = dict(self.extra) if self.extra else {}
        call_extra = kwargs.get("extra")
        if isinstance(call_extra, Mapping):
            merged.update(call_extra)
        updated = dict(kwargs)
        updated["extra"] = merged
        return msg, updated


def _sanitize_value(value: object) -> Any:
    """Sanitize a single arg/extra/bound value for emission.

    Plain ``None``/``bool``/``int``/``float`` values cannot carry credentials
    and pass through untouched (preserving JSON types); strings go through
    the P0-005 sanitizer; anything else is stringified first and then
    sanitized so its text cannot leak either.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_exception_message(value)
    return sanitize_exception_message(_safe_str(value))


class JsonFormatter(logging.Formatter):
    """Format records as single-line JSON with the exact stable key set.

    Always present: ``timestamp`` (UTC ISO-8601, ``…Z``), ``level``,
    ``logger``, ``service``, ``component`` (``null`` when unbound), ``event``,
    ``message``, ``extra`` (object, possibly empty). Conditional: ``camera_id``
    / ``incident_id`` (only when bound/provided, non-``None``) and ``error``
    (``{type, message}``, sanitized, only when ``exc_info`` carries an
    exception). Tracebacks are never rendered, so they cannot leak secrets.
    """

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "service": _sanitize_value(getattr(record, "service", "unknown")),
            "component": _sanitize_value(getattr(record, "component", None)),
            "event": _sanitize_value(getattr(record, "event", None) or DEFAULT_EVENT),
            "message": self._format_message(record),
        }
        camera_id = getattr(record, "camera_id", None)
        if camera_id is not None:
            data["camera_id"] = _sanitize_value(camera_id)
        incident_id = getattr(record, "incident_id", None)
        if incident_id is not None:
            data["incident_id"] = _sanitize_value(incident_id)
        data["extra"] = self._format_extra(record)
        error = self._format_error(record)
        if error is not None:
            data["error"] = error
        return json.dumps(data, ensure_ascii=False)

    def _format_message(self, record: logging.LogRecord) -> str:
        """Render ``msg % args`` with every part sanitized before and after."""
        args = record.args
        if not args:
            return sanitize_exception_message(_safe_str(record.msg))
        sanitized_msg = sanitize_exception_message(_safe_str(record.msg))
        if isinstance(args, Mapping):
            safe_args: Any = {key: _sanitize_value(val) for key, val in args.items()}
        else:
            try:
                seq = tuple(args)
            except TypeError:
                seq = (_sanitize_value(args),)
            else:
                seq = tuple(_sanitize_value(item) for item in seq)
            safe_args = seq
        try:
            rendered = sanitized_msg % safe_args
        except Exception:
            rendered = sanitized_msg + " " + sanitize_exception_message(_safe_str(args))
        return sanitize_exception_message(rendered)

    def _format_extra(self, record: logging.LogRecord) -> dict[str, Any]:
        """Collect non-stable caller fields; key-mask then sanitize each value."""
        raw = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_ATTRS
            and key not in _STABLE_ATTRS
            and not key.startswith("_")
        }
        if not raw:
            return {}
        redacted = redact_mapping(raw)
        return {key: _sanitize_value(value) for key, value in redacted.items()}

    def _format_error(self, record: logging.LogRecord) -> dict[str, str] | None:
        """Serialize ``exc_info`` as sanitized ``{type, message}`` (no traceback)."""
        exc_info = record.exc_info
        if not exc_info:
            return None
        exc_type, exc_value, _traceback = exc_info
        if exc_type is None:
            return None
        return {
            "type": sanitize_exception_message(_safe_str(getattr(exc_type, "__name__", "Error"))),
            "message": sanitize_exception_message(_safe_str(exc_value)),
        }


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure the ``eldercare`` root logger for JSON-to-stderr output.

    Validates *level* against ``DEBUG/INFO/WARNING/ERROR/CRITICAL``
    (case-insensitive); anything else raises ``ValueError`` naming the bad
    value and leaves the logger untouched. Idempotent: repeated calls update
    the level/formatter on the single managed ``StreamHandler(stderr)``
    instead of adding duplicate handlers.
    """
    normalized = level.upper() if isinstance(level, str) else ""
    if normalized not in _VALID_LEVELS:
        raise ValueError(
            f"invalid log level: {level!r} (expected one of {', '.join(_VALID_LEVELS)})"
        )
    numeric = getattr(logging, normalized)
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(numeric)
    managed = [handler for handler in root.handlers if getattr(handler, _MANAGED_ATTR, False)]
    for duplicate in managed[1:]:
        root.removeHandler(duplicate)
    if managed:
        handler = managed[0]
        handler.setLevel(numeric)
        handler.setFormatter(JsonFormatter())
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(numeric)
        handler.setFormatter(JsonFormatter())
        setattr(handler, _MANAGED_ATTR, True)
        root.addHandler(handler)
    return root


def get_logger(service: str, component: str | None = None, **bound: Any) -> logging.LoggerAdapter:
    """Return a logger with ``service``/``component``/extras bound to every record.

    Non-string bound values are stringified safely at bind time (and every
    value is sanitized again at format time), so they are never logged raw.
    Override the event code per call with ``extra={"event": "<dotted.code>"}``.
    """
    stringified = {
        key: value if isinstance(value, str) else _safe_str(value) for key, value in bound.items()
    }
    extra: dict[str, Any] = {"service": service, "component": component}
    extra.update(stringified)
    child = logging.getLogger(f"{ROOT_LOGGER_NAME}.{service}")
    return BoundLogger(child, extra)
