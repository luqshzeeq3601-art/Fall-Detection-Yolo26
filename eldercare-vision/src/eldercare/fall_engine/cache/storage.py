"""Atomic disk storage and provenance verification for keypoint cache files (P4-006)."""

from __future__ import annotations

import gzip
import os
import tempfile
from pathlib import Path

from eldercare.fall_engine.cache.schema import CachedKeypointSequence
from eldercare.fall_engine.cache.serialization import (
    deserialize_sequence_from_json,
    serialize_sequence_to_json,
)


def save_keypoint_cache(
    sequence: CachedKeypointSequence,
    target_path: str | Path,
    *,
    compress: bool = False,
    indent: int | None = 2,
) -> Path:
    """Save a CachedKeypointSequence to disk with atomic write semantics.

    If target_path ends with '.gz' or compress=True, writes a gzip-compressed file.
    """
    if not isinstance(sequence, CachedKeypointSequence):
        raise TypeError(f"sequence must be a CachedKeypointSequence, got {type(sequence).__name__}")

    dest = Path(target_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    is_gz = compress or dest.suffix.lower() == ".gz"
    json_data = serialize_sequence_to_json(sequence, indent=indent)

    # Write to a temporary file in the same directory for atomic replace
    temp_prefix = f".tmp_{dest.name}_"
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=temp_prefix, delete=False) as tmp_file:
        temp_path = Path(tmp_file.name)
        try:
            if is_gz:
                with gzip.GzipFile(fileobj=tmp_file, mode="wb") as gz_out:
                    gz_out.write(json_data.encode("utf-8"))
            else:
                tmp_file.write(json_data.encode("utf-8"))
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    # Atomic rename/replace
    temp_path.replace(dest)
    return dest


def load_keypoint_cache(file_path: str | Path) -> CachedKeypointSequence:
    """Load and validate a CachedKeypointSequence from disk."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Keypoint cache file not found: {path}")

    is_gz = path.suffix.lower() == ".gz"
    if is_gz:
        with gzip.open(path, "rt", encoding="utf-8") as gz_in:
            json_str = gz_in.read()
    else:
        with open(path, encoding="utf-8") as f_in:
            json_str = f_in.read()

    return deserialize_sequence_from_json(json_str)


def validate_cache_provenance(
    sequence: CachedKeypointSequence,
    *,
    expected_model: str | None = None,
    expected_sample_id: str | None = None,
) -> bool:
    """Validate that a cached sequence satisfies all provenance and safety requirements.

    Fails closed (returns False or raises ValueError) if:
    - is_derived is not True
    - is_ground_truth is not False
    - total_frames does not match actual frames
    - expected_model does not match
    - expected_sample_id does not match
    """
    if not isinstance(sequence, CachedKeypointSequence):
        return False

    meta = sequence.metadata
    if not meta.is_derived or meta.is_ground_truth:
        return False

    if meta.total_frames != len(sequence.frames):
        return False

    if expected_model is not None and meta.model_name != expected_model:
        return False

    if expected_sample_id is not None and meta.source_sample_id != expected_sample_id:
        return False

    return True
