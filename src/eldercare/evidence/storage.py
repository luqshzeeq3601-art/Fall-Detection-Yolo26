"""Secure Evidence Storage Engine with Sandboxing and SHA-256 Integrity (P5-003)."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import BinaryIO


class EvidenceStorageError(Exception):
    """Base exception for evidence storage operations."""


class PathTraversalError(EvidenceStorageError):
    """Raised when a path attempts to escape the sandboxed evidence directory."""


class ChecksumMismatchError(EvidenceStorageError):
    """Raised when an evidence file fails cryptographic SHA-256 integrity checks."""


class EvidenceFileNotFoundError(EvidenceStorageError):
    """Raised when a requested evidence file does not exist."""


def compute_sha256(content: bytes) -> str:
    """Compute the hexadecimal SHA-256 digest of a byte sequence."""
    return hashlib.sha256(content).hexdigest()


def compute_file_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Compute the hexadecimal SHA-256 digest of a file using chunked streaming."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_mime_type(filename: Path | str) -> str:
    """Resolve MIME type with strict fallbacks for common evidence types."""
    name = str(filename).lower()
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".mp4"):
        return "video/mp4"
    if name.endswith(".webm"):
        return "video/webm"
    if name.endswith(".json"):
        return "application/json"

    guessed, _ = mimetypes.guess_type(str(filename))
    return guessed or "application/octet-stream"


class EvidenceStorage:
    """Sandboxed storage manager for incident snapshots and video recordings."""

    def __init__(self, base_dir: Path | str = "evidence") -> None:
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)
        # Dedicated temp directory inside evidence tree for atomic writes
        self._tmp_dir = self._base_dir / ".tmp"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        """Return the canonical root directory of the evidence sandbox."""
        return self._base_dir

    def resolve_safe_path(self, relative_path: Path | str) -> Path:
        """Resolve and validate a relative path against the sandboxed base directory.

        Raises:
            PathTraversalError: If path contains null bytes, UNC escapes, or resolves
                                outside the base directory.
        """
        raw_str = str(relative_path)
        if "\0" in raw_str:
            raise PathTraversalError("Null bytes are forbidden in evidence paths.")

        # Reject absolute paths, root slashes, or drive letters
        if (
            raw_str.startswith(("/", "\\"))
            or Path(raw_str).is_absolute()
            or (len(raw_str) > 1 and raw_str[1] == ":")
        ):
            raise PathTraversalError(
                f"Absolute or root paths are forbidden in evidence paths: '{relative_path}'"
            )

        # Treat "\" as a separator on every OS so Windows-style traversal
        # ("..\\..\\x") is caught on POSIX too; stored paths always use "/".
        target = (self._base_dir / raw_str.replace("\\", "/")).resolve()

        try:
            # Python 3.9+ path containment check
            is_inside = target.is_relative_to(self._base_dir)
        except AttributeError:  # pragma: no cover
            is_inside = os.path.commonpath([str(self._base_dir), str(target)]) == str(
                self._base_dir
            )

        if not is_inside:
            raise PathTraversalError(
                f"Path traversal detected: '{relative_path}' resolves outside '{self._base_dir}'."
            )

        return target

    def save_file(
        self,
        relative_path: Path | str,
        content: bytes,
        expected_sha256: str | None = None,
    ) -> tuple[str, int, str]:
        """Save binary content to a sandboxed file and verify SHA-256 checksum.

        Returns:
            Tuple of (normalized relative path, byte count, computed SHA-256).
        Raises:
            PathTraversalError: If path escapes sandbox.
            ChecksumMismatchError: If expected_sha256 does not match computed SHA-256.
        """
        target = self.resolve_safe_path(relative_path)
        computed_hash = compute_sha256(content)

        if expected_sha256 and expected_sha256.lower() != computed_hash.lower():
            raise ChecksumMismatchError(
                f"SHA-256 mismatch for '{relative_path}': "
                f"expected '{expected_sha256}', computed '{computed_hash}'."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        norm_rel = str(target.relative_to(self._base_dir)).replace("\\", "/")
        return norm_rel, len(content), computed_hash

    def save_stream(
        self,
        relative_path: Path | str,
        stream: BinaryIO,
        expected_sha256: str | None = None,
        chunk_size: int = 65536,
    ) -> tuple[str, int, str]:
        """Stream binary content to a temp file and atomically move upon SHA-256 verification.

        Returns:
            Tuple of (normalized relative path, byte count, computed SHA-256).
        """
        target = self.resolve_safe_path(relative_path)
        hasher = hashlib.sha256()
        total_bytes = 0

        temp_file = tempfile.NamedTemporaryFile(dir=self._tmp_dir, delete=False, prefix="ev_write_")
        temp_path = Path(temp_file.name)

        try:
            with temp_file as f:
                while chunk := stream.read(chunk_size):
                    hasher.update(chunk)
                    f.write(chunk)
                    total_bytes += len(chunk)

            computed_hash = hasher.hexdigest()
            if expected_sha256 and expected_sha256.lower() != computed_hash.lower():
                raise ChecksumMismatchError(
                    f"SHA-256 mismatch for streamed evidence '{relative_path}': "
                    f"expected '{expected_sha256}', computed '{computed_hash}'."
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replace
            os.replace(temp_path, target)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

        norm_rel = str(target.relative_to(self._base_dir)).replace("\\", "/")
        return norm_rel, total_bytes, computed_hash

    def read_file(self, relative_path: Path | str, verify_sha256: str | None = None) -> bytes:
        """Read full binary content from a sandboxed evidence file.

        Raises:
            EvidenceFileNotFoundError: If file does not exist.
            ChecksumMismatchError: If verify_sha256 is supplied and content has been tampered.
        """
        target = self.resolve_safe_path(relative_path)
        if not target.is_file():
            raise EvidenceFileNotFoundError(f"Evidence file '{relative_path}' not found.")

        content = target.read_bytes()
        if verify_sha256:
            computed = compute_sha256(content)
            if computed.lower() != verify_sha256.lower():
                raise ChecksumMismatchError(
                    f"Integrity check failed for '{relative_path}': "
                    f"expected '{verify_sha256}', got '{computed}'."
                )

        return content

    def open_stream(
        self, relative_path: Path | str, chunk_size: int = 65536
    ) -> Generator[bytes, None, None]:
        """Yield chunks of binary content for high-efficiency media streaming."""
        target = self.resolve_safe_path(relative_path)
        if not target.is_file():
            raise EvidenceFileNotFoundError(f"Evidence file '{relative_path}' not found.")

        with open(target, "rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    def verify_file_integrity(self, relative_path: Path | str, expected_sha256: str) -> bool:
        """Verify if the file on disk matches the expected SHA-256 checksum."""
        target = self.resolve_safe_path(relative_path)
        if not target.is_file():
            return False
        computed = compute_file_sha256(target)
        return computed.lower() == expected_sha256.lower()

    def exists(self, relative_path: Path | str) -> bool:
        """Check whether an evidence file exists in the sandbox."""
        try:
            target = self.resolve_safe_path(relative_path)
            return target.is_file()
        except PathTraversalError:
            return False

    def delete_file(self, relative_path: Path | str) -> bool:
        """Delete an evidence file safely within the sandbox."""
        target = self.resolve_safe_path(relative_path)
        if target.is_file():
            target.unlink()
            return True
        return False
