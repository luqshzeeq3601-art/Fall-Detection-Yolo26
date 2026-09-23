"""Unit tests for evidence and privacy boundary security (P10-002)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from eldercare.agents.privacy import (
    EvidenceFileNotFoundError,
    EvidencePrivacyBoundary,
    PathTraversalAttemptError,
    UnauthorizedFileExtensionError,
)


@pytest.fixture
def evidence_workspace(tmp_path: Path) -> tuple[EvidencePrivacyBoundary, Path]:
    evidence_dir = tmp_path / "evidence_store"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Create authorized sample files
    (evidence_dir / "snapshot_01.jpg").write_bytes(b"jpeg_data_bytes")
    (evidence_dir / "clip_01.mp4").write_bytes(b"mp4_data_bytes")

    # Create subfolder with authorized file
    sub_dir = evidence_dir / "camera_east"
    sub_dir.mkdir()
    (sub_dir / "frame_100.png").write_bytes(b"png_data_bytes")

    # Create unauthorized file inside evidence dir
    (evidence_dir / "secret.env").write_text("API_KEY=secret123")
    (evidence_dir / "script.sh").write_text("#!/bin/bash\nrm -rf /")

    # Create outside sensitive file
    outside_file = tmp_path / "outside_secret.txt"
    outside_file.write_text("TOP_SECRET_CREDENTIALS")

    boundary = EvidencePrivacyBoundary(evidence_root=evidence_dir)
    return boundary, evidence_dir


class TestPathContainmentAndExtensionValidation:
    """Test filesystem containment, path traversal mitigation, and extension allowlisting."""

    def test_valid_relative_paths_resolve_correctly(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, evidence_dir = evidence_workspace
        resolved = boundary.validate_and_resolve_media_path("snapshot_01.jpg")
        assert resolved == (evidence_dir / "snapshot_01.jpg").resolve()

        resolved_sub = boundary.validate_and_resolve_media_path("camera_east/frame_100.png")
        assert resolved_sub == (evidence_dir / "camera_east" / "frame_100.png").resolve()

    def test_valid_absolute_path_within_root(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, evidence_dir = evidence_workspace
        abs_path = (evidence_dir / "clip_01.mp4").resolve()
        resolved = boundary.validate_and_resolve_media_path(abs_path)
        assert resolved == abs_path

    def test_reject_directory_traversal_attempts(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        traversal_payloads = [
            "../outside_secret.txt",
            "..\\outside_secret.txt",
            "camera_east/../../outside_secret.txt",
            "../../../../etc/passwd",
            "..\\..\\..\\Windows\\System32\\cmd.exe",
        ]
        for payload in traversal_payloads:
            with pytest.raises(PathTraversalAttemptError):
                boundary.validate_and_resolve_media_path(payload)

    def test_reject_null_byte_injection(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        with pytest.raises(PathTraversalAttemptError, match="Null byte"):
            boundary.validate_and_resolve_media_path("snapshot_01.jpg\x00.exe")

    def test_reject_unauthorized_extensions(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        unauthorized_files = [
            "secret.env",
            "script.sh",
            "config.yaml",
            "model.py",
        ]
        for bad_file in unauthorized_files:
            with pytest.raises(UnauthorizedFileExtensionError):
                boundary.validate_and_resolve_media_path(bad_file)

    def test_reject_non_existent_file(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        with pytest.raises(EvidenceFileNotFoundError):
            boundary.validate_and_resolve_media_path("missing_frame_999.jpg")


class TestContextSanitization:
    """Test allowlist-based incident payload sanitization and credential scrubbing."""

    def test_sanitizes_incident_allowlisted_fields_only(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        raw_payload: dict[str, Any] = {
            "incident_id": "inc-12345",
            "camera_id": "cam-living-room",
            "track_id": "track-1",
            "started_at": "2026-09-23T12:00:00Z",
            "confirmed_at": "2026-09-23T12:00:02Z",
            "fall_score": 0.92,
            "detector_state": "FALL_CONFIRMED",
            "internal_rtsp_url": "rtsp://admin:supersecret@192.168.1.100:554/live",
            "database_connection": "postgresql://postgres:dbpass@localhost:5432/eldercare",
            "system_root": "C:\\Users\\Admin\\AppData\\Local\\eldercare",
            "stack_trace": "File '/var/eldercare/core.py', line 45, in execute",
            "evidence_features": {
                "aspect_ratio": 0.45,
                "posture_ratio": 0.38,
                "torso_angle_deg": 78.5,
                "motion_energy": 12.4,
                "internal_db_id": 9999,
                "debug_buffer_pointer": "0x7fff5fbff8",
            },
        }

        sanitized = boundary.sanitize_incident_payload(raw_payload)

        # Allowlisted fields present
        assert sanitized["incident_id"] == "inc-12345"
        assert sanitized["camera_id"] == "cam-living-room"
        assert sanitized["fall_score"] == 0.92
        assert "aspect_ratio" in sanitized["evidence_features"]
        assert "torso_angle_deg" in sanitized["evidence_features"]

        # Forbidden/unauthorized top-level keys removed
        assert "internal_rtsp_url" not in sanitized
        assert "database_connection" not in sanitized
        assert "system_root" not in sanitized
        assert "stack_trace" not in sanitized

        # Forbidden feature keys removed
        assert "internal_db_id" not in sanitized["evidence_features"]
        assert "debug_buffer_pointer" not in sanitized["evidence_features"]

    def test_scrubs_embedded_credentials_and_system_paths_in_strings(
        self, evidence_workspace: tuple[EvidencePrivacyBoundary, Path]
    ) -> None:
        boundary, _ = evidence_workspace
        payload: dict[str, Any] = {
            "incident_id": "inc-sec",
            "camera_id": "camera_rtsp://user:pass123@10.0.0.1/feed",
            "detector_state": "Error in /etc/shadow or C:\\Windows\\System32\\drivers",
        }

        sanitized = boundary.sanitize_incident_payload(payload)
        assert "user:pass123" not in sanitized["camera_id"]
        assert "[REDACTED_URI]" in sanitized["camera_id"]
        assert "/etc/shadow" not in sanitized["detector_state"]
        assert "C:\\Windows\\System32" not in sanitized["detector_state"]
