"""Unit tests for EvidenceStorage file operations and SHA-256 integrity (P5-003)."""

import io
from pathlib import Path

import pytest

from eldercare.evidence.storage import (
    EvidenceStorage,
    compute_file_sha256,
    compute_sha256,
    get_mime_type,
)


@pytest.fixture
def evidence_sandbox(tmp_path: Path) -> EvidenceStorage:
    """Create an isolated evidence storage sandbox in a temp directory."""
    return EvidenceStorage(base_dir=tmp_path / "evidence")


class TestEvidenceStorageOperations:
    """Test suite verifying save, stream, read, verify, and delete operations."""

    def test_save_and_read_file(self, evidence_sandbox: EvidenceStorage) -> None:
        """Verify binary file write and read with SHA-256 validation."""
        sample_data = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 128  # dummy JPEG
        expected_hash = compute_sha256(sample_data)

        rel_path, byte_count, computed_hash = evidence_sandbox.save_file(
            relative_path="cam_01/snapshots/snap_1.jpg",
            content=sample_data,
            expected_sha256=expected_hash,
        )

        assert rel_path == "cam_01/snapshots/snap_1.jpg"
        assert byte_count == len(sample_data)
        assert computed_hash == expected_hash

        # Read back with hash verification
        read_content = evidence_sandbox.read_file(rel_path, verify_sha256=expected_hash)
        assert read_content == sample_data

    def test_save_and_read_stream(self, evidence_sandbox: EvidenceStorage) -> None:
        """Verify streaming binary writes and chunked streaming reads."""
        video_payload = b"ftypisom" + (b"A" * 100_000)
        expected_hash = compute_sha256(video_payload)
        stream_in = io.BytesIO(video_payload)

        rel_path, byte_count, computed_hash = evidence_sandbox.save_stream(
            relative_path="cam_02/clips/fall_event.mp4",
            stream=stream_in,
            expected_sha256=expected_hash,
            chunk_size=4096,
        )

        assert rel_path == "cam_02/clips/fall_event.mp4"
        assert byte_count == len(video_payload)
        assert computed_hash == expected_hash

        # Verify integrity
        assert evidence_sandbox.verify_file_integrity(rel_path, expected_hash) is True

        # Open stream and read chunks
        chunks = list(evidence_sandbox.open_stream(rel_path, chunk_size=8192))
        reconstructed = b"".join(chunks)
        assert reconstructed == video_payload

    def test_exists_and_delete_file(self, evidence_sandbox: EvidenceStorage) -> None:
        """Verify exists check and safe file deletion."""
        rel_path, _, _ = evidence_sandbox.save_file(
            relative_path="test/delete_me.txt",
            content=b"temporary content",
        )
        assert evidence_sandbox.exists(rel_path) is True
        assert evidence_sandbox.delete_file(rel_path) is True
        assert evidence_sandbox.exists(rel_path) is False
        # Deleting again returns False
        assert evidence_sandbox.delete_file(rel_path) is False

    def test_get_mime_type_helper(self) -> None:
        """Verify MIME type detection across known formats."""
        assert get_mime_type("frame.jpg") == "image/jpeg"
        assert get_mime_type("frame.jpeg") == "image/jpeg"
        assert get_mime_type("frame.png") == "image/png"
        assert get_mime_type("clip.mp4") == "video/mp4"
        assert get_mime_type("clip.webm") == "video/webm"
        assert get_mime_type("meta.json") == "application/json"
        assert get_mime_type("unknown.xyz123") == "application/octet-stream"

    def test_compute_file_sha256_utility(self, tmp_path: Path) -> None:
        """Verify standalone compute_file_sha256 utility."""
        test_file = tmp_path / "hash_test.bin"
        content = b"Deterministic payload 123456"
        test_file.write_bytes(content)

        file_hash = compute_file_sha256(test_file)
        direct_hash = compute_sha256(content)
        assert file_hash == direct_hash
