"""Frozen artifacts registry and checksum verification for fall engine splits and configuration."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

# Canonical SHA-256 digests established in ADR-005 (computed over LF-normalized contents)
FROZEN_ARTIFACT_DIGESTS: Mapping[str, str] = {
    "config/fall_detection.yaml": (
        "b56152c7dae9f604d53eb7feac0ed2659f54ffdc57b531827206d8548aed9532"
    ),
    "datasets/manifests/urfd_manifest.csv": (
        "6df450e36b2d6309b5aaa4133e6dcc28b4d51cb17ca5eacff93549f4a3134cb1"
    ),
    "datasets/manifests/upfall_manifest.csv": (
        "53f5e8f35a360aff59b4ce3b0532e7f1f661762e79367a91046d0a39752baa1f"
    ),
    "datasets/manifests/local_manifest.csv": (
        "3bc17a1e73efba5526c821d49d0b76a60ca74c7d499e076eefc2d997c4e7f053"
    ),
}


def compute_file_sha256(path: Path | str, normalize_newlines: bool = True) -> str:
    """Compute SHA-256 digest of a file with newline normalization.

    Parameters
    ----------
    path : Path | str
        Path to the target file.
    normalize_newlines : bool
        If True, normalizes CRLF line endings to LF before hashing.

    Returns
    -------
    str
        Hexadecimal SHA-256 digest string.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Target file for checksum computation does not exist: {p}")

    raw_bytes = p.read_bytes()
    if normalize_newlines:
        raw_bytes = raw_bytes.replace(b"\r\n", b"\n")

    return hashlib.sha256(raw_bytes).hexdigest()


def find_repository_root(start_path: Path | str | None = None) -> Path:
    """Find the repository root containing config and datasets directories.

    Parameters
    ----------
    start_path : Path | str | None
        Starting directory for upward traversal. Defaults to current working directory.

    Returns
    -------
    Path
        Resolved repository root directory path.
    """
    current = Path(start_path).resolve() if start_path else Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        has_config = (candidate / "config" / "fall_detection.yaml").is_file()
        has_manifests = (candidate / "datasets" / "manifests").is_dir()
        if has_config and has_manifests:
            return candidate
    return current


def verify_frozen_artifacts(repo_root: Path | str | None = None) -> dict[str, bool]:
    """Verify all frozen dataset manifests and config files against expected SHA-256 digests.

    Parameters
    ----------
    repo_root : Path | str | None
        Optional explicit repository root. If None, resolves root automatically.

    Returns
    -------
    dict[str, bool]
        Mapping from relative artifact path to boolean status indicating whether the hash matches.
    """
    root = find_repository_root(repo_root)
    results: dict[str, bool] = {}

    for rel_path, expected_hash in FROZEN_ARTIFACT_DIGESTS.items():
        file_path = root / rel_path
        if not file_path.is_file():
            results[rel_path] = False
            continue
        computed_hash = compute_file_sha256(file_path, normalize_newlines=True)
        results[rel_path] = computed_hash.lower() == expected_hash.lower()

    return results


def assert_frozen_artifacts_intact(repo_root: Path | str | None = None) -> None:
    """Assert that all frozen dataset manifests and config files match expected SHA-256 digests.

    Raises
    ------
    RuntimeError
        If any frozen artifact is missing or has a checksum mismatch.
    """
    root = find_repository_root(repo_root)
    verification = verify_frozen_artifacts(root)
    failed = [rel_path for rel_path, is_valid in verification.items() if not is_valid]

    if failed:
        mismatches = []
        for rel_path in failed:
            file_path = root / rel_path
            if not file_path.is_file():
                mismatches.append(f"  - {rel_path}: File not found at {file_path}")
            else:
                curr_hash = compute_file_sha256(file_path, normalize_newlines=True)
                exp_hash = FROZEN_ARTIFACT_DIGESTS[rel_path]
                mismatches.append(
                    f"  - {rel_path}: Hash mismatch (expected {exp_hash}, got {curr_hash})"
                )

        error_msg = "Frozen artifacts integrity verification failed (ADR-005):\n" + "\n".join(
            mismatches
        )
        raise RuntimeError(error_msg)
