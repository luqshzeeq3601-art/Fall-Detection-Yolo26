"""V4 Real-World Dataset Acquisition & Ingestion Protocol (P11.7-006).

Governs dataset ingestion across genuine optical video sources (URFD, UP-Fall, LocalUAT),
enforces cryptographic SHA-256 checksums, extracts video container metadata,
validates optical authenticity against synthetic renders, and enforces split isolation.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from eldercare.fall_engine.evaluation.split_guard import DatasetSplitGuard, SplitLeakageError

logger = logging.getLogger("dataset_ingestion")


class DatasetSource(str, Enum):
    """Recognized dataset sources."""

    URFD = "URFD"
    UP_FALL = "UP-Fall"
    LOCAL_UAT = "LocalUAT"
    HOSPITAL_CLINICAL = "HospitalClinical"


@dataclass(frozen=True)
class OpticalAuthenticityScore:
    """Quantitative metrics for distinguishing optical capture from synthetic rendering."""

    unique_color_count: int
    laplacian_variance: float
    color_std: float
    is_optical_capture: bool
    authenticity_score: float
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpticalAuthenticityValidator:
    """Discriminates genuine camera optical captures from flat synthetic OpenCV animations.

    Real camera captures feature lens aberration, optical sensor grain, high chromatic
    diversity, and natural surface textures. Procedural animations generated via OpenCV
    drawing primitives exhibit flat monochrome planes and minimal unique colors.
    """

    def __init__(
        self,
        min_unique_colors: int = 800,
        min_laplacian_var: float = 200.0,
        min_color_std: float = 35.0,
    ) -> None:
        self.min_unique_colors = min_unique_colors
        self.min_laplacian_var = min_laplacian_var
        self.min_color_std = min_color_std

    def validate_frame(self, frame: np.ndarray) -> tuple[int, float, float]:
        """Compute optical authenticity statistics on a single frame."""
        # Subsample grid to measure unique 24-bit color diversity
        sub = frame[::4, ::4]
        unique_colors = len(np.unique(sub.reshape(-1, 3), axis=0))

        # Laplacian variance on grayscale measures sensor noise and fine edge textures
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Global color standard deviation
        color_std = float(frame.std())

        return unique_colors, lap_var, color_std

    def validate_video(
        self, video_path: Path | str, sample_count: int = 5
    ) -> OpticalAuthenticityScore:
        """Sample frames throughout video and assess whether it is genuine optical capture."""
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open video file: {path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return OpticalAuthenticityScore(
                unique_color_count=0,
                laplacian_variance=0.0,
                color_std=0.0,
                is_optical_capture=False,
                authenticity_score=0.0,
                rejection_reason="Empty or unreadable video stream",
            )

        indices = np.linspace(0, max(0, total_frames - 1), sample_count, dtype=int)
        colors_list = []
        laps_list = []
        stds_list = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            uc, lap, std = self.validate_frame(frame)
            colors_list.append(uc)
            laps_list.append(lap)
            stds_list.append(std)

        cap.release()

        if not colors_list:
            return OpticalAuthenticityScore(
                unique_color_count=0,
                laplacian_variance=0.0,
                color_std=0.0,
                is_optical_capture=False,
                authenticity_score=0.0,
                rejection_reason="No frames could be successfully decoded",
            )

        avg_colors = int(np.mean(colors_list))
        avg_lap = float(np.mean(laps_list))
        avg_std = float(np.mean(stds_list))

        # Check thresholds
        fails = []
        if avg_colors < self.min_unique_colors:
            fails.append(f"unique colors {avg_colors} < {self.min_unique_colors}")
        if avg_lap < self.min_laplacian_var:
            fails.append(f"laplacian var {avg_lap:.1f} < {self.min_laplacian_var:.1f}")
        if avg_std < self.min_color_std:
            fails.append(f"color std {avg_std:.1f} < {self.min_color_std:.1f}")

        is_optical = len(fails) == 0
        score = min(
            1.0,
            (avg_colors / (self.min_unique_colors * 2) * 0.4)
            + (avg_lap / (self.min_laplacian_var * 2) * 0.4)
            + (avg_std / (self.min_color_std * 2) * 0.2),
        )

        reason = None if is_optical else f"Synthetic/flat render detected ({', '.join(fails)})"

        return OpticalAuthenticityScore(
            unique_color_count=avg_colors,
            laplacian_variance=round(avg_lap, 2),
            color_std=round(avg_std, 2),
            is_optical_capture=is_optical,
            authenticity_score=round(score, 4),
            rejection_reason=reason,
        )


@dataclass
class IngestedVideoMetadata:
    """Comprehensive metadata ledger entry for an ingested video sequence."""

    sample_id: str
    source_dataset: str
    sequence_id: str
    subject_id: str
    camera_id: str
    activity: str
    is_fall: bool
    fall_type: str
    path_local: str
    split: str
    license: str
    sha256: str
    frame_count: int
    fps: float
    duration_seconds: float
    width: int
    height: int
    codec: str
    deployment_evidence: bool
    optical_authenticity: OpticalAuthenticityScore
    fall_start_frame: int | None = None
    fall_end_frame: int | None = None
    lying_start_frame: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["optical_authenticity"] = self.optical_authenticity.to_dict()
        return d

    def to_csv_row(self) -> dict[str, str]:
        return {
            "sample_id": self.sample_id,
            "source_dataset": self.source_dataset,
            "sequence_id": self.sequence_id,
            "subject_id": self.subject_id,
            "camera_id": self.camera_id,
            "activity": self.activity,
            "is_fall": "1" if self.is_fall else "0",
            "fall_type": self.fall_type,
            "path_local": self.path_local,
            "split": self.split,
            "license": self.license,
            "sha256": self.sha256,
            "frame_count": str(self.frame_count),
            "fps": f"{self.fps:.2f}",
            "duration_seconds": f"{self.duration_seconds:.3f}",
            "width": str(self.width),
            "height": str(self.height),
            "deployment_evidence": "1" if self.deployment_evidence else "0",
            "fall_start_frame": (
                str(self.fall_start_frame) if self.fall_start_frame is not None else ""
            ),
            "fall_end_frame": str(self.fall_end_frame) if self.fall_end_frame is not None else "",
            "lying_start_frame": (
                str(self.lying_start_frame) if self.lying_start_frame is not None else ""
            ),
            "notes": self.notes,
        }


def compute_file_sha256(file_path: Path | str) -> str:
    """Compute exact SHA-256 cryptographic digest of a binary file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class DatasetIngestionEngine:
    """Orchestrates dataset scanning, validation, and manifest generation."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        validator: OpticalAuthenticityValidator | None = None,
    ) -> None:
        self.root = Path(repo_root or Path(__file__).resolve().parents[4])
        self.validator = validator or OpticalAuthenticityValidator()
        self.split_guard = DatasetSplitGuard(self.root)

    def parse_urfd_ground_truth(
        self, ground_truth_csv: Path | str
    ) -> dict[str, tuple[int | None, int | None, int | None]]:
        """Parse urfall-cam0-falls.csv for start, impact, and lying frame indices.

        Returns:
            Dict mapping sequence_id (e.g. 'fall-01') to
            (fall_start_frame, fall_end_frame, lying_start_frame).
        """
        p = Path(ground_truth_csv)
        if not p.is_file():
            logger.warning(f"URFD ground truth CSV not found: {p}")
            return {}

        frames_by_fall: dict[str, list[tuple[int, int]]] = {}
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 3:
                    seq = parts[0].strip()
                    try:
                        f_idx = int(parts[1].strip())
                        lbl = int(parts[2].strip())
                        frames_by_fall.setdefault(seq, []).append((f_idx, lbl))
                    except ValueError:
                        continue

        intervals: dict[str, tuple[int | None, int | None, int | None]] = {}
        for seq, items in frames_by_fall.items():
            items.sort(key=lambda x: x[0])
            falling = [f_idx for f_idx, lbl in items if lbl == 0]
            lying = [f_idx for f_idx, lbl in items if lbl == 1]
            f_start = falling[0] if falling else None
            f_end = falling[-1] if falling else None
            l_start = lying[0] if lying else None
            intervals[seq] = (f_start, f_end, l_start)

        return intervals

    def ingest_urfd(
        self,
        raw_dir: Path | str | None = None,
        manifest_csv: Path | str | None = None,
        ground_truth_csv: Path | str | None = None,
    ) -> list[IngestedVideoMetadata]:
        """Ingest all genuine URFD videos and generate verified metadata records."""
        raw_path = Path(raw_dir or (self.root / "datasets" / "raw" / "urfd"))
        manifest_path = Path(
            manifest_csv or (self.root / "datasets" / "manifests" / "urfd_manifest.csv")
        )
        gt_path = Path(
            ground_truth_csv or (self.root / "datasets" / "raw" / "urfd" / "urfall-cam0-falls.csv")
        )

        if not raw_path.is_dir():
            raise FileNotFoundError(f"URFD raw directory not found: {raw_path}")
        if not manifest_path.is_file():
            raise FileNotFoundError(f"URFD manifest not found: {manifest_path}")

        # Load reference rows from manifest
        with open(manifest_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            ref_rows = {r["sequence_id"]: r for r in reader}

        # Parse ground-truth fall intervals
        gt_intervals = self.parse_urfd_ground_truth(gt_path)

        # Scan raw videos
        mp4_files = sorted(raw_path.glob("*.mp4"))
        if not mp4_files:
            raise ValueError(f"No MP4 files found in {raw_path}")

        records: list[IngestedVideoMetadata] = []

        for mp4 in mp4_files:
            # Extract sequence_id from filename e.g. 'fall-01-cam0.mp4' -> 'fall-01'
            base = mp4.stem
            seq_id = base.replace("-cam0", "")
            ref = ref_rows.get(seq_id)

            if ref is None:
                logger.warning(f"Video {mp4.name} has no matching entry in reference manifest.")
                continue

            # Compute raw file sha256
            file_sha256 = compute_file_sha256(mp4)

            # Probe container properties via OpenCV
            cap = cv2.VideoCapture(str(mp4))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
            cap.release()

            codec = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
            duration = frame_cnt / fps if fps > 0 else 0.0

            # Validate optical authenticity
            auth = self.validator.validate_video(mp4, sample_count=5)

            is_fall = ref["is_fall"].strip().lower() in ("1", "true", "fall", "yes")
            f_start, f_end, l_start = gt_intervals.get(seq_id, (None, None, None))

            # Deployment evidence invariant: requires authentic optical capture
            deployment_evidence = auth.is_optical_capture

            # Compute relative path
            try:
                rel_path = str(mp4.relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel_path = f"datasets/raw/urfd/{mp4.name}"

            rec = IngestedVideoMetadata(
                sample_id=ref["sample_id"],
                source_dataset="URFD",
                sequence_id=seq_id,
                subject_id=ref["subject_id"],
                camera_id=ref["camera_id"],
                activity=ref["activity"],
                is_fall=is_fall,
                fall_type=ref["fall_type"],
                path_local=rel_path,
                split=ref["split"].strip().lower(),
                license=ref["license"],
                sha256=file_sha256,
                frame_count=frame_cnt,
                fps=round(fps, 2),
                duration_seconds=round(duration, 3),
                width=w,
                height=h,
                codec=codec,
                deployment_evidence=deployment_evidence,
                optical_authenticity=auth,
                fall_start_frame=f_start,
                fall_end_frame=f_end,
                lying_start_frame=l_start,
                notes=ref["notes"],
            )
            records.append(rec)

        return records

    def compile_master_manifest(
        self,
        records: list[IngestedVideoMetadata],
        output_json: Path | str,
        output_csv: Path | str,
    ) -> dict[str, Any]:
        """Validate partition isolation and write unified JSON and CSV manifests."""
        out_json = Path(output_json)
        out_csv = Path(output_csv)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_csv.parent.mkdir(parents=True, exist_ok=True)

        # Enforce split isolation invariants via DatasetSplitGuard
        dict_records = [r.to_dict() for r in records]
        verification = self.split_guard.verify_partitions(
            dict_records, train_split="dev", dev_split="dev", holdout_split="test"
        )

        # Summary statistics
        total_videos = len(records)
        total_frames = sum(r.frame_count for r in records)
        total_duration = sum(r.duration_seconds for r in records)
        fall_count = sum(1 for r in records if r.is_fall)
        adl_count = total_videos - fall_count
        authentic_count = sum(1 for r in records if r.deployment_evidence)

        stats = {
            "total_videos": total_videos,
            "total_frames": total_frames,
            "total_duration_seconds": round(total_duration, 2),
            "total_duration_hours": round(total_duration / 3600.0, 4),
            "fall_sequences": fall_count,
            "adl_sequences": adl_count,
            "authentic_optical_videos": authentic_count,
            "synthetic_quarantined_videos": total_videos - authentic_count,
            "partition_verification": verification,
        }

        # Write JSON master manifest
        manifest_payload = {
            "schema_version": "v4.0.0",
            "metadata": {
                "generated_by": "DatasetIngestionEngine",
                "task": "P11.7-006",
                "timestamp": "2026-09-25T21:30:00Z",
                "summary": stats,
            },
            "records": dict_records,
        }
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(manifest_payload, f, indent=2)

        # Write CSV master manifest
        csv_fieldnames = [
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
            "sha256",
            "frame_count",
            "fps",
            "duration_seconds",
            "width",
            "height",
            "deployment_evidence",
            "fall_start_frame",
            "fall_end_frame",
            "lying_start_frame",
            "notes",
        ]
        with open(out_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(r.to_csv_row())

        return stats

    def verify_manifest_integrity(self, manifest_json: Path | str) -> dict[str, Any]:
        """Verify on-disk video files against manifest hashes and properties."""
        p = Path(manifest_json)
        if not p.is_file():
            raise FileNotFoundError(f"Manifest JSON not found: {p}")

        with open(p, encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records", [])
        mismatches = []
        verified_count = 0

        for r in records:
            rel = r["path_local"]
            disk_path = self.root / rel
            if not disk_path.is_file():
                mismatches.append(f"Missing file on disk: {disk_path}")
                continue

            current_hash = compute_file_sha256(disk_path)
            if current_hash != r["sha256"]:
                mismatches.append(
                    f"SHA256 mismatch for {r['sample_id']}: "
                    f"expected {r['sha256'][:10]}..., got {current_hash[:10]}..."
                )
                continue

            verified_count += 1

        if mismatches:
            raise SplitLeakageError(
                f"Manifest integrity verification failed ({len(mismatches)} errors): {mismatches}"
            )

        return {
            "status": "PASS",
            "verified_records": verified_count,
            "total_records": len(records),
        }
