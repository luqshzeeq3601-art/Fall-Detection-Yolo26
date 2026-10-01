"""Strict evidence and privacy boundary for Agent/VLM enrichment (P10-002).

Enforces:
1. Filesystem isolation: only verified media within the evidence storage directory is accessible.
2. Allowlist sanitization: sensitive metadata (RTSP URLs, credentials, stack traces, host paths)
   is blocked or redacted before transmission to AI providers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from eldercare.common.redaction import sanitize_exception_message

ALLOWED_MEDIA_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".mp4"})

ALLOWED_INCIDENT_FIELDS = frozenset(
    {
        "incident_id",
        "camera_id",
        "track_id",
        "started_at",
        "confirmed_at",
        "fall_score",
        "detector_state",
        "evidence_features",
    }
)

ALLOWED_FEATURE_FIELDS = frozenset(
    {
        "aspect_ratio",
        "posture_ratio",
        "torso_angle_deg",
        "vertical_velocity",
        "motion_energy",
        "keypoint_confidence_mean",
        "duration_seconds",
        "peak_fall_score",
        "transition_count",
    }
)

# Regex to detect and sanitize connection strings, RTSP/HTTP URLs with auth, and system paths
_SENSITIVE_URI_PATTERN = re.compile(
    r"(?:rtsp|rtsps|http|https|postgresql|postgres|mqtt|mqtts)://[^\s@/]+(?::[^\s@/]+)?@[^\s/]+",
    re.IGNORECASE,
)
_WINDOWS_PATH_PATTERN = re.compile(r"[a-zA-Z]:\\(?:[^\s\\/:*?\"<>|]+\\)+[^\s\\/:*?\"<>|]*")
_UNIX_PATH_PATTERN = re.compile(r"/(?:etc|var|usr|home|root|proc|sys|opt|bin)/[^\s]+")


class PrivacyBoundaryError(Exception):
    """Base exception for privacy boundary violations."""


class PathTraversalAttemptError(PrivacyBoundaryError):
    """Raised when an evidence path attempts directory traversal or root escape."""


class UnauthorizedFileExtensionError(PrivacyBoundaryError):
    """Raised when an evidence file extension is not in the approved media allowlist."""


class EvidenceFileNotFoundError(PrivacyBoundaryError):
    """Raised when a referenced evidence file does not exist on disk."""


class EvidencePrivacyBoundary:
    """Manages secure access to media evidence and metadata sanitization for Agent/VLM."""

    def __init__(self, evidence_root: str | Path) -> None:
        self._evidence_root = Path(evidence_root).resolve()

    @property
    def evidence_root(self) -> Path:
        """Configured base directory for verified media evidence."""
        return self._evidence_root

    def validate_and_resolve_media_path(self, relative_or_absolute_path: str | Path) -> Path:
        """Validate that a requested evidence path is safe, exists, and is inside evidence_root.

        Raises:
            PathTraversalAttemptError: if path tries to escape evidence_root.
            UnauthorizedFileExtensionError: if extension is not an approved media format.
            EvidenceFileNotFoundError: if target file does not exist or is not a regular file.
        """
        raw_path = Path(relative_or_or_str := str(relative_or_absolute_path).strip())

        # Check for null byte injections
        if "\x00" in relative_or_or_str:
            raise PathTraversalAttemptError("Null byte detected in evidence path")

        # Resolve candidate path
        if raw_path.is_absolute():
            candidate = raw_path.resolve()
        else:
            # Windows path syntax in a non-absolute path (a drive letter, or "\" that
            # POSIX would treat as a filename character) is rejected or normalised so
            # traversal is caught the same way on every OS.
            if len(relative_or_or_str) > 1 and relative_or_or_str[1] == ":":
                raise PathTraversalAttemptError(
                    f"Path '{relative_or_absolute_path}' uses a drive letter outside evidence root"
                )
            normalised = relative_or_or_str.replace("\\", "/")
            candidate = (self._evidence_root / normalised).resolve()

        # Enforce filesystem containment within evidence_root
        try:
            candidate.relative_to(self._evidence_root)
        except ValueError as exc:
            raise PathTraversalAttemptError(
                f"Path '{relative_or_absolute_path}' escapes evidence root directory"
            ) from exc

        # Enforce approved media extension
        extension = candidate.suffix.lower()
        if extension not in ALLOWED_MEDIA_EXTENSIONS:
            raise UnauthorizedFileExtensionError(
                f"Extension '{extension}' is not an authorized media format. "
                f"Allowed: {sorted(ALLOWED_MEDIA_EXTENSIONS)}"
            )

        # Enforce file existence and regular file constraint
        if not candidate.is_file():
            raise EvidenceFileNotFoundError(f"Evidence file not found at '{candidate}'")

        return candidate

    def sanitize_incident_payload(self, raw_incident: dict[str, Any]) -> dict[str, Any]:
        """Filter incident dictionary strictly against the allowlist and sanitize string values.

        Returns:
            Sanitized dictionary containing only approved analytical context.
        """
        sanitized: dict[str, Any] = {}

        for key, val in raw_incident.items():
            if key not in ALLOWED_INCIDENT_FIELDS:
                continue

            if key == "evidence_features" and isinstance(val, dict):
                # Filter features dictionary against feature allowlist
                filtered_features: dict[str, Any] = {}
                for f_key, f_val in val.items():
                    if f_key in ALLOWED_FEATURE_FIELDS:
                        filtered_features[f_key] = self._sanitize_value(f_val)
                sanitized[key] = filtered_features
            else:
                sanitized[key] = self._sanitize_value(val)

        return sanitized

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively scrub sensitive strings, URLs, credentials, and paths."""
        if isinstance(value, str):
            # 1. Apply standard secret/token redaction
            cleaned = sanitize_exception_message(value)
            # 2. Redact sensitive URIs containing authentication
            cleaned = _SENSITIVE_URI_PATTERN.sub("[REDACTED_URI]", cleaned)
            # 3. Redact local OS paths
            cleaned = _WINDOWS_PATH_PATTERN.sub("[REDACTED_PATH]", cleaned)
            cleaned = _UNIX_PATH_PATTERN.sub("[REDACTED_PATH]", cleaned)
            return cleaned
        if isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        return value
