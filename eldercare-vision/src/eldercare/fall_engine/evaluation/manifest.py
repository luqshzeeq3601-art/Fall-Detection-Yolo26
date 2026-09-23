"""Dataset manifest parser and integrity validation (P4-005).

Loads and verifies sequence manifests for URFD, UP-Fall, and local UAT datasets,
strictly enforcing sequence-level split isolation and zero data leakage.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SequenceManifestRecord:
    """Metadata and split assignment for a single video sequence / sample."""

    sample_id: str
    source_dataset: str
    sequence_id: str
    subject_id: str
    camera_id: str
    activity: str
    is_fall: bool
    fall_type: str
    path_local: str
    split: str  # "dev" or "test"
    license: str
    notes: str


def load_manifest(manifest_path: Path | str) -> list[SequenceManifestRecord]:
    """Parse a CSV manifest file and validate record integrity.

    Args:
        manifest_path: Path to the manifest CSV file.

    Returns:
        List of parsed SequenceManifestRecord instances.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        ValueError: If required columns are missing or split integrity is violated.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")

    required_columns = {
        "sample_id",
        "source_dataset",
        "sequence_id",
        "subject_id",
        "camera_id",
        "activity",
        "is_fall",
        "fall_type",
        "path_local",
        "split",
        "license",
        "notes",
    }

    records: list[SequenceManifestRecord] = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty or corrupted manifest file: {path}")

        missing_cols = required_columns - set(reader.fieldnames)
        if missing_cols:
            raise ValueError(
                f"Manifest {path.name} missing required columns: {sorted(missing_cols)}"
            )

        for row_num, row in enumerate(reader, start=2):
            is_fall_raw = row["is_fall"].strip().lower()
            is_fall = is_fall_raw in ("1", "true", "yes", "fall")
            split = row["split"].strip().lower()
            if split not in ("dev", "test"):
                raise ValueError(
                    f"Invalid split '{row['split']}' in {path.name} row {row_num}; "
                    "must be 'dev' or 'test'"
                )

            rec = SequenceManifestRecord(
                sample_id=row["sample_id"].strip(),
                source_dataset=row["source_dataset"].strip(),
                sequence_id=row["sequence_id"].strip(),
                subject_id=row["subject_id"].strip(),
                camera_id=row["camera_id"].strip(),
                activity=row["activity"].strip(),
                is_fall=is_fall,
                fall_type=row["fall_type"].strip(),
                path_local=row["path_local"].strip(),
                split=split,
                license=row["license"].strip(),
                notes=row["notes"].strip(),
            )
            records.append(rec)

    validate_manifest_integrity(records)
    return records


def validate_manifest_integrity(records: Sequence[SequenceManifestRecord]) -> None:
    """Validate that sample IDs are unique and sequence IDs do not cross dev/test splits.

    Raises:
        ValueError: If duplicate sample_ids or sequence split leakage is detected.
    """
    sample_ids: set[str] = set()
    dev_sequences: set[str] = set()
    test_sequences: set[str] = set()

    for rec in records:
        if rec.sample_id in sample_ids:
            raise ValueError(f"Duplicate sample_id found in manifest: '{rec.sample_id}'")
        sample_ids.add(rec.sample_id)

        if rec.split == "dev":
            dev_sequences.add(rec.sequence_id)
        elif rec.split == "test":
            test_sequences.add(rec.sequence_id)

    # Check for split leakage (same sequence_id in both dev and test)
    overlap = dev_sequences.intersection(test_sequences)
    if overlap:
        raise ValueError(
            f"Data leakage detected! Sequences in both dev and test: {sorted(overlap)}"
        )
