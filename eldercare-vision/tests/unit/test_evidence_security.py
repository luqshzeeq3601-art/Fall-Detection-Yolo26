"""Security and adversarial tests for EvidenceStorage sandbox (P5-003)."""

from pathlib import Path

import pytest

from eldercare.evidence.storage import (
    ChecksumMismatchError,
    EvidenceFileNotFoundError,
    EvidenceStorage,
    PathTraversalError,
)


@pytest.fixture
def evidence_sandbox(tmp_path: Path) -> EvidenceStorage:
    """Create isolated sandbox for security tests."""
    return EvidenceStorage(base_dir=tmp_path / "safe_evidence")


class TestEvidenceSecurity:
    """Security test suite validating path traversal defense and tamper detection."""

    @pytest.mark.parametrize(
        "malicious_path",
        [
            "../secret.txt",
            "../../etc/passwd",
            "..\\..\\windows\\system32\\calc.exe",
            "foo/../../bar/../../escape.jpg",
            "/etc/shadow",
            "C:\\Windows\\System32\\cmd.exe",
            "subdir/../../../root.bin",
        ],
        ids=[
            "parent_dir",
            "unix_root_escape",
            "windows_root_escape",
            "nested_traversal",
            "absolute_unix",
            "absolute_win",
            "deep_traversal",
        ],
    )
    def test_path_traversal_attempts_blocked_on_save(
        self, evidence_sandbox: EvidenceStorage, malicious_path: str
    ) -> None:
        """Verify all forms of path traversal are blocked with PathTraversalError."""
        with pytest.raises(PathTraversalError):
            evidence_sandbox.save_file(
                relative_path=malicious_path,
                content=b"malicious write",
            )

    def test_null_byte_path_injection_blocked(self, evidence_sandbox: EvidenceStorage) -> None:
        """Verify null byte injection is rejected."""
        with pytest.raises(PathTraversalError, match="Null bytes are forbidden"):
            evidence_sandbox.resolve_safe_path("legit_image.jpg\0.png")

    def test_checksum_mismatch_on_save_aborts_write(
        self, evidence_sandbox: EvidenceStorage
    ) -> None:
        """Verify save fails immediately when expected SHA-256 does not match."""
        payload = b"Genuine data"
        bogus_sha = "0" * 64

        with pytest.raises(ChecksumMismatchError):
            evidence_sandbox.save_file(
                relative_path="cam_01/tampered.jpg",
                content=payload,
                expected_sha256=bogus_sha,
            )

        # File should not exist on disk
        assert evidence_sandbox.exists("cam_01/tampered.jpg") is False

    def test_checksum_mismatch_on_read_detects_disk_tampering(
        self, evidence_sandbox: EvidenceStorage
    ) -> None:
        """Verify read_file detects external modification/tampering on disk."""
        rel_path, _, valid_hash = evidence_sandbox.save_file(
            relative_path="cam_01/tamper_target.jpg",
            content=b"Original content",
        )

        # Directly tamper the file on disk behind storage engine's back
        disk_path = evidence_sandbox.resolve_safe_path(rel_path)
        disk_path.write_bytes(b"Tampered corrupted content")

        with pytest.raises(ChecksumMismatchError):
            evidence_sandbox.read_file(rel_path, verify_sha256=valid_hash)

    def test_missing_file_raises_evidence_not_found(
        self, evidence_sandbox: EvidenceStorage
    ) -> None:
        """Verify reading a missing file raises EvidenceFileNotFoundError."""
        with pytest.raises(EvidenceFileNotFoundError):
            evidence_sandbox.read_file("non_existent_path.jpg")

        with pytest.raises(EvidenceFileNotFoundError):
            list(evidence_sandbox.open_stream("non_existent_stream.mp4"))
