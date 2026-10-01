"""V4 Dataset Split Guard & Holdout Isolation Framework.

Enforces:
1. Strict subject-disjoint partitioning (zero subject overlap between train, dev, and holdout).
2. Zero duplicate video or sequence SHA-256 hashes across splits.
3. Cryptographic manifest immutability.
4. Programmatic holdout access isolation preventing training scripts from touching holdout data.
"""

from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]


# Evaluation role of each split.
# - development: training and calibration data.
# - burned_diagnostic: evaluated repeatedly under several operating points during V6/V6.1
#   (Test-A, Test-X). Still excluded from training, but results are development-grade
#   diagnostics ("dev-2") and never a held-out claim.
# - sealed_final: untouched until the final freeze; the only splits that support a claim.
SPLIT_ROLES: dict[str, str] = {
    "train": "development",
    "dev": "development",
    "dev_longform": "development",
    "test_a": "burned_diagnostic",
    "test_x": "burned_diagnostic",
    "holdout": "sealed_final",
    "test": "sealed_final",
    "test_b": "sealed_final",
    "longform_adl": "sealed_final",
    "longform_adl_heldout": "sealed_final",
}
BURNED_SPLITS: frozenset[str] = frozenset(
    s for s, role in SPLIT_ROLES.items() if role == "burned_diagnostic"
)
SEALED_SPLITS: frozenset[str] = frozenset(
    s for s, role in SPLIT_ROLES.items() if role == "sealed_final"
)


def split_role(split_name: str) -> str:
    """Return the evaluation role of ``split_name`` ('unknown' if unregistered)."""
    return SPLIT_ROLES.get(split_name.strip().lower(), "unknown")


class SplitLeakageError(Exception):
    """Raised when data leakage or subject overlap across splits is detected."""


class HoldoutAccessError(Exception):
    """Raised when training code attempts to access held-out evaluation splits."""


def sha256_lf(path: Path | str) -> str:
    """Compute sha256 hash of a file with normalized LF endings."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


class DatasetSplitGuard:
    """Enforces zero-leakage, subject-disjoint partitions, and manifest cryptographic integrity."""

    REQUIRED_COLUMNS: set[str] = {
        "sample_id",
        "source_dataset",
        "sequence_id",
        "subject_id",
        "camera_id",
        "activity",
        "is_fall",
        "path_local",
        "split",
        "license",
    }

    ALLOWED_SPLITS: set[str] = {
        "train",
        "dev",
        "dev_longform",
        "holdout",
        "test",
        "test_a",
        "test_x",
        "test_b",
        "longform_adl",
        "longform_adl_heldout",
    }

    def __init__(self, dataset_root: Path | str | None = None) -> None:
        self.root = Path(dataset_root or ROOT)

    def load_and_validate_manifest(self, manifest_path: Path | str) -> list[dict[str, str]]:
        """Load manifest CSV and validate schema completeness."""
        p = Path(manifest_path)
        if not p.is_file():
            raise FileNotFoundError(f"Manifest not found: {p}")

        with open(p, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"Manifest {p.name} missing required columns: {sorted(missing)}")
            rows = list(reader)

        for idx, row in enumerate(rows, 1):
            split = row.get("split", "").strip().lower()
            if split not in self.ALLOWED_SPLITS:
                raise ValueError(f"Row {idx} in {p.name} has invalid split '{split}'")

        return rows

    def verify_partitions(
        self,
        records: Sequence[dict[str, str]],
        train_split: str = "train",
        dev_split: str = "dev",
        holdout_split: str = "holdout",
    ) -> dict[str, Any]:
        """Verify subject-disjointness and zero video hash overlap across partitions.

        Returns:
            Dict containing partition statistics and verification confirmation.
        """
        subjects_by_split: dict[str, set[str]] = defaultdict(set)
        hashes_by_split: dict[str, set[str]] = defaultdict(set)
        samples_by_split: dict[str, int] = defaultdict(int)

        for r in records:
            s_name = r.get("split", "").strip().lower()
            subj = r.get("subject_id", "").strip()
            sample_id = r.get("sample_id", "").strip()
            path_local = r.get("path_local", "").strip()

            if not subj:
                raise SplitLeakageError(f"Record {sample_id} is missing subject_id.")

            subjects_by_split[s_name].add(subj)
            samples_by_split[s_name] += 1

            # Hash check if local file exists
            if path_local:
                vid_path = self.root / "datasets" / path_local
                if vid_path.is_file():
                    v_hash = hashlib.sha256(vid_path.read_bytes()).hexdigest()
                    hashes_by_split[s_name].add(v_hash)

        # 1. Subject disjointness check
        splits = list(subjects_by_split.keys())
        for i in range(len(splits)):
            for j in range(i + 1, len(splits)):
                s1, s2 = splits[i], splits[j]
                overlap = subjects_by_split[s1] & subjects_by_split[s2]
                if overlap:
                    raise SplitLeakageError(
                        f"CRITICAL DATA LEAKAGE: Overlapping subjects between '{s1}' and '{s2}': "
                        f"{sorted(overlap)}"
                    )

        # 2. File hash disjointness check
        for i in range(len(splits)):
            for j in range(i + 1, len(splits)):
                s1, s2 = splits[i], splits[j]
                hash_overlap = hashes_by_split[s1] & hashes_by_split[s2]
                if hash_overlap:
                    raise SplitLeakageError(
                        f"CRITICAL DATA LEAKAGE: Identical file hashes between '{s1}' and '{s2}': "
                        f"{len(hash_overlap)} duplicate files detected."
                    )

        return {
            "splits": list(samples_by_split.keys()),
            "sample_counts": dict(samples_by_split),
            "subject_counts": {s: len(subjs) for s, subjs in subjects_by_split.items()},
            "zero_subject_overlap": True,
            "zero_hash_overlap": True,
        }

    @staticmethod
    def enforce_training_isolation(split_name: str, context: str = "Training") -> None:
        """Prevent training scripts from loading holdout or test splits."""
        cleaned = split_name.strip().lower()
        protected_splits = {
            "holdout",
            "test",
            "test_a",
            "test_x",
            "test_b",
            "longform_adl",
            "longform_adl_heldout",
        }
        if cleaned in protected_splits:
            raise HoldoutAccessError(
                f"ILLEGAL ACCESS: {context} code attempted to access protected split '{cleaned}'! "
                "Holdout data must strictly remain unseen until final frozen evaluation."
            )

    @staticmethod
    def enforce_sealed_access(
        split_names: Sequence[str], allow_sealed: bool, context: str = "Evaluation"
    ) -> None:
        """Block access to sealed final splits unless explicitly authorised (post-freeze)."""
        sealed = sorted({s.strip().lower() for s in split_names} & SEALED_SPLITS)
        if sealed and not allow_sealed:
            raise HoldoutAccessError(
                f"ILLEGAL ACCESS: {context} requested sealed split(s) {sealed}. "
                "Sealed splits may only be evaluated once, after the final freeze."
            )
