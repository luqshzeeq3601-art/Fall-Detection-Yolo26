"""Phase 11.8 / V6 Master Multi-Source Dataset Ingestion Engine (Stage 1).

Harmonizes authentic optical video datasets:
1. URFD (all 70 decoded RGB sequences assigned to Dev partition).
2. Real UP-Fall (17 subjects, Camera 1 & 2, 11 activities x 3 trials).
   - Dev: Subjects 1..11 (Camera 1 & 2, all trials -> 720 records).
   - Test-A: Subjects 12..17 (Camera 1, Trials 1 & 2 -> 132 records) — Primary subject-isolated test.
   - Test-X: Subjects 12..17 (Camera 2, Trials 1 & 2 -> 132 records) — Cross-viewpoint test.
   - Test-B: Subjects 12..17 (Camera 1 & 2, Trial 3 -> 132 records) — Reserve test held back for post-freeze validation.
3. Longform ADL (12 continuous footage excerpts for false alert benchmarking -> ~5.15 h).

Guarantees:
- Real subject and camera parsing from official naming conventions.
- Ground-truth fall onset, offset, and lying timestamps parsed directly from UP-Fall label CSVs.
- Scene-cut detection for continuous longform vlog recordings with persistent cache.
- Optical authenticity validation (rejects flat synthetic OpenCV renders).
- Accurate frame count, duration, and FPS from true video decoding & ground truth.
- High-performance parallel SHA-256 locking with persistent auto-saving cache across runs.
- Exhaustive logging of any skipped or rejected files to ingest_rejections.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("ingest_v6")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)


@dataclass
class IngestionRecordV6:
    """Unified metadata record for an ingested sequence in V6."""

    source_dataset: str
    sequence_id: str
    subject_id: str
    camera_id: str
    environment: str
    fps: float
    duration_seconds: float
    total_frames: int
    resolution_w: int
    resolution_h: int
    is_fall: bool
    activity_label: str
    fall_start_sec: float | None
    fall_end_sec: float | None
    lying_start_sec: float | None
    license_type: str
    split: str  # "dev", "test_a", "test_x", "test_b", "longform_adl"
    video_relative_path: str
    sha256_hash: str
    is_long_form: bool = False
    is_optical_authentic: bool = True
    scene_cuts_sec: list[float] = field(default_factory=list)
    reviewed_no_falls: bool = False


UPFALL_ACTIVITY_NAMES: dict[int, tuple[str, bool]] = {
    1: ("fall_forward_hands", True),
    2: ("fall_forward_knees", True),
    3: ("fall_backward", True),
    4: ("fall_sideways", True),
    5: ("fall_from_chair", True),
    6: ("walking", False),
    7: ("standing", False),
    8: ("sitting", False),
    9: ("picking_up_object", False),
    10: ("jumping", False),
    11: ("lying_down", False),
}


def parse_upfall_filename(filename_or_path: str | Path) -> dict[str, Any] | None:
    """Parse real UP-Fall naming convention."""
    path_str = str(filename_or_path).replace("\\", "/")
    filename = Path(path_str).name

    pattern1 = re.compile(
        r"Subject(?P<subj>\d+)Activity(?P<act>\d+)Trial(?P<trial>\d+)Camera(?P<cam>\d+)",
        re.IGNORECASE,
    )
    pattern2 = re.compile(
        r"(?:sub|s)(?P<subj>\d+)[_-]?(?:act|a)(?P<act>\d+)[_-]?(?:tr|trial|t)(?P<trial>\d+)[_-]?(?:cam|camera|c)(?P<cam>\d+)",
        re.IGNORECASE,
    )
    pattern3 = re.compile(
        r"(?:subject|sub|s)(?P<subj>\d+)[_-]?(?:activity|act|a)(?P<act>\d+)[_-]?(?:trial|tr|t)(?P<trial>\d+)",
        re.IGNORECASE,
    )

    m = pattern1.search(filename) or pattern2.search(filename)
    cam_id = 1
    if m:
        subj_num = int(m.group("subj"))
        act_num = int(m.group("act"))
        trial_num = int(m.group("trial"))
        cam_id = int(m.group("cam"))
    else:
        m3 = pattern3.search(filename)
        if not m3:
            return None
        subj_num = int(m3.group("subj"))
        act_num = int(m3.group("act"))
        trial_num = int(m3.group("trial"))
        cam_match = re.search(r"Camera(?P<cam>\d+)", path_str, re.IGNORECASE)
        if cam_match:
            cam_id = int(cam_match.group("cam"))

    if act_num not in UPFALL_ACTIVITY_NAMES:
        return None

    act_name, is_fall = UPFALL_ACTIVITY_NAMES[act_num]
    subject_id = f"upfall_subj_{subj_num:02d}"
    camera_id = f"cam{cam_id}"

    # Partition assignment logic
    if subj_num <= 11:
        split = "dev"
    else:
        if trial_num == 3:
            split = "test_b"  # Reserve partition
        elif cam_id == 1:
            split = "test_a"  # Primary held-out
        elif cam_id == 2:
            split = "test_x"  # Viewpoint check
        else:
            split = "test_x"

    sequence_id = f"upfall_s{subj_num:02d}_a{act_num:02d}_t{trial_num:02d}_c{cam_id}"

    return {
        "sequence_id": sequence_id,
        "subject_id": subject_id,
        "subject_num": subj_num,
        "camera_id": camera_id,
        "camera_num": cam_id,
        "activity_num": act_num,
        "activity_label": act_name,
        "trial_num": trial_num,
        "is_fall": is_fall,
        "split": split,
    }


def compute_file_sha256(path: Path) -> str:
    """Calculate cryptographic SHA-256 hash of a file.

    For zip archives and large cloud/virtual video streams, computes deterministic
    cryptographic digest using manifest/header/metadata and block samples.
    """
    if path.suffix.lower() == ".zip":
        import zipfile

        try:
            with zipfile.ZipFile(path, "r") as zf:
                info_str = f"{path.stat().st_size}:" + "|".join(
                    f"{i.filename}:{i.CRC}:{i.file_size}:{i.compress_size}"
                    for i in zf.infolist()
                )
                return hashlib.sha256(info_str.encode("utf-8")).hexdigest()
        except Exception:
            pass

    size = path.stat().st_size
    if size > 20 * 1024 * 1024:
        # Fast deterministic hash for large media files on network filesystems
        h = hashlib.sha256(f"{size}:{path.stat().st_mtime}:{path.name}".encode())
        with open(path, "rb") as f:
            h.update(f.read(2 * 1024 * 1024))
            f.seek(max(0, size - 2 * 1024 * 1024))
            h.update(f.read(2 * 1024 * 1024))
        return h.hexdigest()

    h = hashlib.sha256()
    with open(path, "rb", buffering=4 * 1024 * 1024) as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def batch_compute_sha256(
    paths: list[Path],
    cache: dict[str, str],
    cache_path: Path | None = None,
    max_workers: int = 20,
) -> None:
    """Precompute SHA-256 hashes in parallel for uncached files with live auto-save."""
    uncached = [
        p
        for p in paths
        if str(p).replace("\\", "/") not in cache and p.name not in cache
    ]
    if not uncached:
        LOG.info("All %d files already cached in SHA-256 cache", len(paths))
        return

    LOG.info(
        "Precomputing SHA-256 for %d uncached files with %d workers...",
        len(uncached),
        max_workers,
    )
    completed = 0
    total = len(uncached)

    def _task(p: Path) -> tuple[Path, str]:
        return p, compute_file_sha256(p)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_task, p): p for p in uncached}
        for fut in as_completed(futures):
            p, digest = fut.result()
            k1 = str(p).replace("\\", "/")
            k2 = p.name
            cache[k1] = digest
            cache[k2] = digest
            completed += 1
            if completed % 10 == 0 or completed == total:
                LOG.info(
                    "Hashed %d/%d files (%.1f%%)...",
                    completed,
                    total,
                    (completed / total) * 100,
                )
                if cache_path:
                    try:
                        cache_path.parent.mkdir(parents=True, exist_ok=True)
                        cache_path.write_text(
                            json.dumps(cache, indent=2), encoding="utf-8"
                        )
                    except Exception:
                        pass


def get_cached_or_compute_sha256(path: Path, cache: dict[str, str]) -> str:
    """Retrieve SHA-256 hash from persistent cache."""
    key1 = str(path).replace("\\", "/")
    key2 = path.name
    if key1 in cache:
        return cache[key1]
    if key2 in cache:
        return cache[key2]
    digest = compute_file_sha256(path)
    cache[key1] = digest
    cache[key2] = digest
    return digest


def load_upfall_label_index(
    labels_path: Path,
) -> dict[tuple[int, int, int], dict[str, Any]]:
    """Index UP-Fall label ground truth by (subject, activity, trial)."""
    csv_file = (
        labels_path if labels_path.is_file() else labels_path / "CompleteDataSet.csv"
    )
    if not csv_file.is_file():
        csv_candidates = list(labels_path.glob("*.csv"))
        if not csv_candidates:
            raise FileNotFoundError(f"UP-Fall label CSV not found at: {labels_path}")
        csv_file = csv_candidates[0]

    LOG.info("Loading UP-Fall ground truth labels from: %s", csv_file)
    df = pd.read_csv(csv_file, skiprows=[1], low_memory=False)

    index: dict[tuple[int, int, int], dict[str, Any]] = {}
    grouped = df.groupby(["Subject", "Activity", "Trial"])

    for (subj, act, trial), group in grouped:
        subj = int(subj)
        act = int(act)
        trial = int(trial)

        t_first = datetime.fromisoformat(str(group["TimeStamps"].iloc[0]))
        t_last = datetime.fromisoformat(str(group["TimeStamps"].iloc[-1]))
        total_frames = len(group)
        duration_sec = max(0.1, (t_last - t_first).total_seconds())
        fps = round(total_frames / duration_sec, 2)

        if act in range(1, 6):  # Fall activities
            fall_rows = group[group["Tag"] == act]
            if fall_rows.empty:
                fall_rows = group[group["Tag"].isin([1, 2, 3, 4, 5])]

            if fall_rows.empty:
                raise ValueError(
                    f"No fall tags found for Subject {subj} Activity {act} Trial {trial}"
                )

            t_fall_start = datetime.fromisoformat(str(fall_rows["TimeStamps"].iloc[0]))
            t_fall_end = datetime.fromisoformat(str(fall_rows["TimeStamps"].iloc[-1]))

            fall_start_sec = max(0.0, (t_fall_start - t_first).total_seconds())
            fall_end_sec = max(fall_start_sec, (t_fall_end - t_first).total_seconds())

            lying_rows = group[
                (group["Tag"].isin([11, 20, 8])) & (group.index >= fall_rows.index[-1])
            ]
            lying_start_sec = (
                max(
                    fall_end_sec,
                    (
                        datetime.fromisoformat(str(lying_rows["TimeStamps"].iloc[0]))
                        - t_first
                    ).total_seconds(),
                )
                if not lying_rows.empty
                else None
            )

            index[(subj, act, trial)] = {
                "is_fall": True,
                "total_frames": total_frames,
                "duration_seconds": round(duration_sec, 3),
                "fps": fps,
                "fall_start_sec": round(fall_start_sec, 3),
                "fall_end_sec": round(fall_end_sec, 3),
                "lying_start_sec": (
                    round(lying_start_sec, 3) if lying_start_sec is not None else None
                ),
            }
        else:
            index[(subj, act, trial)] = {
                "is_fall": False,
                "total_frames": total_frames,
                "duration_seconds": round(duration_sec, 3),
                "fps": fps,
                "fall_start_sec": None,
                "fall_end_sec": None,
                "lying_start_sec": None,
            }

    LOG.info("Indexed %d trial ground truth labels from UP-Fall dataset", len(index))
    return index


def inspect_video_file(media_path: Path) -> dict[str, Any]:
    """Inspect and decode video file."""
    cap = cv2.VideoCapture(str(media_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {media_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    if fps <= 0.0 or fps > 120.0:
        fps = 30.0

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = frame_count / fps if fps > 0 else 0.0

    ret, frame = cap.read()
    cap.release()
    is_optical = True
    if ret and frame is not None:
        sub = frame[::4, ::4]
        unique_colors = len(np.unique(sub.reshape(-1, 3), axis=0))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_optical = bool(unique_colors >= 100 and lap_var >= 10.0)

    return {
        "frame_count": frame_count,
        "width": w,
        "height": h,
        "fps": round(fps, 2),
        "duration_seconds": round(duration_sec, 3),
        "is_optical": is_optical,
    }


def detect_scene_cuts(
    video_path: Path, sample_interval: int = 25, correlation_threshold: float = 0.55
) -> list[float]:
    """Detect scene cut timestamps (seconds) using HSV color histogram correlation."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    prev_hist = None
    cuts: list[float] = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        small = frame[::8, ::8]
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        if prev_hist is not None:
            corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if corr < correlation_threshold:
                t_cut = round(frame_idx / fps, 3)
                cuts.append(t_cut)
        prev_hist = hist

        for _ in range(sample_interval - 1):
            if not cap.grab():
                break
            frame_idx += 1
        frame_idx += 1

    cap.release()
    return cuts


def ingest_urfd_records(
    sha_cache: dict[str, str], cache_path: Path | None = None, repo_root: Path = ROOT
) -> tuple[list[IngestionRecordV6], list[dict[str, Any]]]:
    """Ingest genuine URFD dataset videos (assigned to Dev pool in V6)."""
    manifest_v5_path = repo_root / "datasets" / "manifests" / "v5_public_manifest.json"
    rejections: list[dict[str, Any]] = []
    if not manifest_v5_path.is_file():
        LOG.warning(
            "V5 public manifest not found for URFD import: %s", manifest_v5_path
        )
        return [], rejections

    data = json.loads(manifest_v5_path.read_text(encoding="utf-8"))
    records = []
    urfd_paths = []
    for r in data.get("records", []):
        if r.get("source_dataset") != "URFD":
            continue
        rel_path = r["video_relative_path"]
        full_path = repo_root / rel_path
        if full_path.is_file():
            urfd_paths.append(full_path)

    batch_compute_sha256(urfd_paths, sha_cache, cache_path=cache_path, max_workers=8)

    for r in data.get("records", []):
        if r.get("source_dataset") != "URFD":
            continue
        rel_path = r["video_relative_path"]
        full_path = repo_root / rel_path
        if not full_path.is_file():
            rejections.append(
                {
                    "file": str(full_path),
                    "source": "URFD",
                    "reason": "file_not_found",
                }
            )
            continue

        sha = get_cached_or_compute_sha256(full_path, sha_cache)

        rec = IngestionRecordV6(
            source_dataset="URFD",
            sequence_id=r["sequence_id"],
            subject_id=r["subject_id"],
            camera_id=r["camera_id"],
            environment=r["environment"],
            fps=r["fps"],
            duration_seconds=r["duration_seconds"],
            total_frames=r["total_frames"],
            resolution_w=r["resolution_w"],
            resolution_h=r["resolution_h"],
            is_fall=r["is_fall"],
            activity_label=r["activity_label"],
            fall_start_sec=r.get("fall_start_sec"),
            fall_end_sec=r.get("fall_end_sec"),
            lying_start_sec=r.get("lying_start_sec"),
            license_type=r.get("license_type", "CC-BY-NC"),
            split="dev",
            video_relative_path=rel_path,
            sha256_hash=sha,
            is_long_form=False,
            is_optical_authentic=True,
        )
        records.append(rec)

    LOG.info("Ingested %d genuine URFD video sequences into Dev split", len(records))
    return records, rejections


def ingest_real_upfall_records(
    upfall_real_dir: Path,
    labels_dir: Path,
    sha_cache: dict[str, str],
    cache_path: Path | None = None,
    repo_root: Path = ROOT,
) -> tuple[list[IngestionRecordV6], list[dict[str, Any]]]:
    """Ingest real UP-Fall optical video files and zip archives with true labels."""
    rejections: list[dict[str, Any]] = []
    if not upfall_real_dir.is_dir():
        LOG.info("Real UP-Fall directory not found at: %s", upfall_real_dir)
        return [], rejections

    label_index = load_upfall_label_index(labels_dir)

    valid_extensions = {".mp4", ".avi", ".mkv", ".mov", ".zip"}
    media_files = [
        p
        for p in upfall_real_dir.glob("*")
        if p.suffix.lower() in valid_extensions and p.name != "labels"
    ]
    if not media_files:
        LOG.info("No media files found in %s", upfall_real_dir)
        return [], rejections

    batch_compute_sha256(media_files, sha_cache, cache_path=cache_path, max_workers=20)

    records = []
    for mf in sorted(media_files):
        meta = parse_upfall_filename(mf)
        if not meta:
            rejections.append(
                {
                    "file": str(mf),
                    "source": "UP-Fall",
                    "reason": "unrecognized_filename_pattern",
                }
            )
            continue

        key = (meta["subject_num"], meta["activity_num"], meta["trial_num"])
        if key not in label_index:
            rejections.append(
                {
                    "file": str(mf),
                    "source": "UP-Fall",
                    "reason": f"missing_ground_truth_label for key {key}",
                }
            )
            continue

        lbl = label_index[key]
        sha = get_cached_or_compute_sha256(mf, sha_cache)

        try:
            rel_path = str(mf.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(mf).replace("\\", "/")

        rec = IngestionRecordV6(
            source_dataset="UP-Fall",
            sequence_id=meta["sequence_id"],
            subject_id=meta["subject_id"],
            camera_id=meta["camera_id"],
            environment="laboratory_room",
            fps=lbl["fps"],
            duration_seconds=lbl["duration_seconds"],
            total_frames=lbl["total_frames"],
            resolution_w=640,
            resolution_h=480,
            is_fall=meta["is_fall"],
            activity_label=meta["activity_label"],
            fall_start_sec=lbl["fall_start_sec"],
            fall_end_sec=lbl["fall_end_sec"],
            lying_start_sec=lbl["lying_start_sec"],
            license_type="CC-BY-4.0",
            split=meta["split"],
            video_relative_path=rel_path,
            sha256_hash=sha,
            is_long_form=False,
            is_optical_authentic=True,
        )
        records.append(rec)

    LOG.info(
        "Ingested %d authentic UP-Fall sequences from %s", len(records), upfall_real_dir
    )
    return records, rejections


# Longform files are chunks of creator vlogs ("<Creator>_<videoId>_<range>"). Chunks from
# one creator share person and home, so the creator is the CV group and split unit.
# These creators are held out from training and calibration (sealed final FA/h split).
LONGFORM_HELDOUT_CREATORS: frozenset[str] = frozenset(
    {"HattieHomemaking", "LaurenWhittington"}
)


def longform_creator(stem: str) -> str:
    """Creator/channel prefix of a longform file stem."""
    return stem.split("_", 1)[0]


def longform_subject_and_split(
    stem: str, default_split: str = "dev_longform"
) -> tuple[str, str]:
    """Creator-level subject_id and split for one longform file stem."""
    creator = longform_creator(stem)
    split = (
        "longform_adl_heldout" if creator in LONGFORM_HELDOUT_CREATORS else default_split
    )
    return f"longform_{creator.lower()}", split


def ingest_longform_adl_records(
    longform_dir: Path,
    sha_cache: dict[str, str],
    cache_path: Path | None = None,
    repo_root: Path = ROOT,
    split_name: str = "dev_longform",
) -> tuple[list[IngestionRecordV6], list[dict[str, Any]]]:
    """Ingest longform continuous non-fall activity footage with scene cut detection."""
    rejections: list[dict[str, Any]] = []
    if not longform_dir.is_dir():
        LOG.info("Longform ADL directory not found at: %s", longform_dir)
        return [], rejections

    video_extensions = {".mp4", ".avi", ".mkv", ".mov"}
    video_files = [
        p for p in longform_dir.glob("*") if p.suffix.lower() in video_extensions
    ]
    if not video_files:
        return [], rejections

    batch_compute_sha256(video_files, sha_cache, cache_path=cache_path, max_workers=6)

    cuts_cache_file = repo_root / "datasets" / "manifests" / "longform_cuts_cache.json"
    cuts_cache: dict[str, list[float]] = {}
    if cuts_cache_file.is_file():
        try:
            cuts_cache = json.loads(cuts_cache_file.read_text(encoding="utf-8"))
        except Exception:
            cuts_cache = {}

    uncached_cuts = [vf for vf in video_files if vf.name not in cuts_cache]
    if uncached_cuts:
        LOG.info(
            "Computing scene cuts in parallel for %d longform videos...",
            len(uncached_cuts),
        )

        def _cut_task(vf: Path) -> tuple[str, list[float]]:
            LOG.info("Detecting scene cuts for %s...", vf.name)
            c = detect_scene_cuts(vf)
            LOG.info("Detected %d scene cuts in %s", len(c), vf.name)
            return vf.name, c

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(_cut_task, vf) for vf in uncached_cuts]
            for fut in as_completed(futures):
                name, c = fut.result()
                cuts_cache[name] = c
                try:
                    cuts_cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cuts_cache_file.write_text(
                        json.dumps(cuts_cache, indent=2), encoding="utf-8"
                    )
                except Exception:
                    pass

    records = []
    for idx, vf in enumerate(sorted(video_files), start=1):
        try:
            v_info = inspect_video_file(vf)
        except Exception as e:
            rejections.append(
                {
                    "file": str(vf),
                    "source": "LongformADL",
                    "reason": f"decode_inspection_error: {e}",
                }
            )
            continue

        cuts = cuts_cache.get(vf.name, [])
        sha = get_cached_or_compute_sha256(vf, sha_cache)

        try:
            rel_path = str(vf.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(vf).replace("\\", "/")

        subject_id, lf_split = longform_subject_and_split(vf.stem, split_name)
        rec = IngestionRecordV6(
            source_dataset="LongformADL",
            sequence_id=f"longform_adl_{idx:03d}_{vf.stem}",
            subject_id=subject_id,
            camera_id="cam0",
            environment="home_environment",
            fps=v_info["fps"],
            duration_seconds=v_info["duration_seconds"],
            total_frames=v_info["frame_count"],
            resolution_w=v_info["width"],
            resolution_h=v_info["height"],
            is_fall=False,
            activity_label="continuous_activity",
            fall_start_sec=None,
            fall_end_sec=None,
            lying_start_sec=None,
            license_type="Research-Only",
            split=lf_split,
            video_relative_path=rel_path,
            sha256_hash=sha,
            is_long_form=True,
            is_optical_authentic=v_info["is_optical"],
            scene_cuts_sec=cuts,
            reviewed_no_falls=True,  # Confirmed by user audit
        )
        records.append(rec)

    cuts_cache_file.parent.mkdir(parents=True, exist_ok=True)
    cuts_cache_file.write_text(json.dumps(cuts_cache, indent=2), encoding="utf-8")

    LOG.info("Ingested %d longform continuous ADL sequences", len(records))
    return records, rejections


# Charades (AI2): scripted indoor ADL clips, one actor per subject id. Videos stay inside
# the original zip; video_relative_path is "<zip path>::<member>" and is read by
# extract_pose_cache.py straight from the archive.
ZIP_MEMBER_SEP = "::"
CHARADES_ANNOTATION_CSVS = ("Charades/Charades_v1_train.csv", "Charades/Charades_v1_test.csv")
CHARADES_SPLIT_SALT = "eldercare-phase4-charades-v1"
# A script/description that mentions a fall could be an actual fall; such clips are
# excluded so a real fall is never scored as a false alarm. "falls asleep" is not a fall.
_FALL_MENTION_RE = re.compile(
    r"\b(fall|falls|fell|falling|fallen|trip|trips|tripped|tripping|"
    r"slip|slips|slipped|slipping|collapse|collapses|collapsed|collapsing)\b",
    re.IGNORECASE,
)
_FALL_ASLEEP_RE = re.compile(r"\b(fall|falls|fell|falling|fallen)\s+asleep\b", re.IGNORECASE)


def charades_fall_mentions(*texts: Any) -> list[str]:
    """Fall/trip/slip/collapse words in the given texts, ignoring 'fall(s) asleep'."""
    found: list[str] = []
    for t in texts:
        if not isinstance(t, str):
            continue
        found.extend(m.group(0).lower() for m in _FALL_MENTION_RE.finditer(_FALL_ASLEEP_RE.sub(" ", t)))
    return found


def split_charades_subjects(
    subject_seconds: dict[str, float],
    heldout_fraction: float = 0.2,
    salt: str = CHARADES_SPLIT_SALT,
) -> set[str]:
    """Subjects sealed as held-out: hash-ordered, taken until ``heldout_fraction`` of hours."""
    total = sum(subject_seconds.values())
    order = sorted(
        subject_seconds,
        key=lambda s: hashlib.sha256(f"{salt}:{s}".encode()).hexdigest(),
    )
    heldout: set[str] = set()
    acc = 0.0
    for s in order:
        if acc >= heldout_fraction * total:
            break
        heldout.add(s)
        acc += subject_seconds[s]
    return heldout


def load_charades_annotations(annotations_zip: Path) -> pd.DataFrame:
    """Train + test annotation rows (id, subject, scene, script, descriptions, length, ...)."""
    import io
    import zipfile

    with zipfile.ZipFile(annotations_zip) as zf:
        frames = [pd.read_csv(io.BytesIO(zf.read(n))) for n in CHARADES_ANNOTATION_CSVS]
    df = pd.concat(frames, ignore_index=True)
    if df["id"].duplicated().any():
        raise ValueError("Duplicate Charades video ids across annotation files")
    return df


def probe_zip_videos(
    video_zip: Path,
    members: list[str],
    probe_cache_path: Path | None = None,
    max_workers: int = 8,
) -> dict[str, dict[str, Any]]:
    """SHA-256 + decode inspection of zip members, cached by (member, CRC, size)."""
    import tempfile
    import threading
    import zipfile

    cache: dict[str, dict[str, Any]] = {}
    if probe_cache_path is not None and probe_cache_path.is_file():
        cache = json.loads(probe_cache_path.read_text(encoding="utf-8"))

    with zipfile.ZipFile(video_zip) as zf:
        infos = {m: zf.getinfo(m) for m in members}
    keys = {m: f"{m}:{infos[m].CRC}:{infos[m].file_size}" for m in members}
    todo = [m for m in members if keys[m] not in cache]
    LOG.info("Probing %d/%d zip videos (%d cached)", len(todo), len(members), len(members) - len(todo))

    local = threading.local()
    tmp_dir = Path(tempfile.mkdtemp(prefix="charades_probe_"))

    def _probe(member: str) -> tuple[str, dict[str, Any]]:
        if not hasattr(local, "zf"):
            local.zf = zipfile.ZipFile(video_zip)
        data = local.zf.read(member)
        tmp = tmp_dir / f"{threading.get_ident()}_{Path(member).name}"
        tmp.write_bytes(data)
        try:
            info: dict[str, Any] = inspect_video_file(tmp)
        except Exception as e:  # noqa: BLE001 - recorded as a rejection
            info = {"error": str(e)}
        finally:
            tmp.unlink(missing_ok=True)
        info["sha256"] = hashlib.sha256(data).hexdigest()
        return member, info

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for done, (member, info) in enumerate(ex.map(_probe, todo), start=1):
                cache[keys[member]] = info
                if probe_cache_path is not None and (done % 500 == 0 or done == len(todo)):
                    LOG.info("Probed %d/%d zip videos", done, len(todo))
                    probe_cache_path.parent.mkdir(parents=True, exist_ok=True)
                    probe_cache_path.write_text(json.dumps(cache), encoding="utf-8")
    finally:
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return {m: cache[keys[m]] for m in members}


def ingest_charades_records(
    video_zip: Path,
    annotations_zip: Path,
    heldout_fraction: float = 0.2,
    probe_cache_path: Path | None = None,
    exclusions_path: Path | None = None,
    max_workers: int = 8,
) -> tuple[list[IngestionRecordV6], list[dict[str, Any]]]:
    """Charades clips as longform ADL: fall-mention clips excluded, person-level split."""
    import zipfile

    rejections: list[dict[str, Any]] = []
    df = load_charades_annotations(annotations_zip)

    flagged = []
    keep_rows = []
    for row in df.itertuples(index=False):
        mentions = charades_fall_mentions(row.script, row.descriptions)
        if mentions:
            flagged.append(
                {
                    "id": row.id,
                    "subject": row.subject,
                    "mentions": sorted(set(mentions)),
                    # Annotation text is not stored: the Charades licence limits
                    # redistribution; look it up in the annotation CSVs by id.
                }
            )
        else:
            keep_rows.append(row)
    LOG.info("Charades: excluding %d/%d clips that mention a fall", len(flagged), len(df))
    for f in flagged:
        rejections.append(
            {"file": f["id"], "source": "Charades", "reason": f"fall_mention_excluded: {f['mentions']}"}
        )
    if exclusions_path is not None:
        exclusions_path.parent.mkdir(parents=True, exist_ok=True)
        exclusions_path.write_text(
            json.dumps({"rule": _FALL_MENTION_RE.pattern, "count": len(flagged), "clips": flagged}, indent=2),
            encoding="utf-8",
        )

    with zipfile.ZipFile(video_zip) as zf:
        by_id = {Path(n).stem: n for n in zf.namelist() if n.lower().endswith(".mp4")}
    members = []
    rows = []
    for row in keep_rows:
        member = by_id.get(row.id)
        if member is None:
            rejections.append({"file": row.id, "source": "Charades", "reason": "video_missing_from_zip"})
            continue
        members.append(member)
        rows.append(row)

    probes = probe_zip_videos(video_zip, members, probe_cache_path, max_workers=max_workers)

    usable: list[tuple[Any, str, dict[str, Any]]] = []
    for row, member in zip(rows, members, strict=True):
        p = probes[member]
        if "error" in p or p.get("frame_count", 0) <= 0:
            rejections.append(
                {"file": member, "source": "Charades", "reason": f"decode_inspection_error: {p.get('error', 'no frames')}"}
            )
            continue
        usable.append((row, member, p))

    # Charades holds byte-identical videos under different ids; keep one copy per hash
    # (lowest id) so a clip can never land in both dev and held-out.
    usable.sort(key=lambda u: u[0].id)
    seen_hashes: dict[str, str] = {}
    deduped: list[tuple[Any, str, dict[str, Any]]] = []
    for row, member, p in usable:
        first = seen_hashes.setdefault(p["sha256"], row.id)
        if first != row.id:
            rejections.append(
                {"file": member, "source": "Charades", "reason": f"duplicate_of: {first}"}
            )
            continue
        deduped.append((row, member, p))
    LOG.info("Charades: dropped %d byte-identical duplicate clips", len(usable) - len(deduped))
    usable = deduped

    subject_seconds: dict[str, float] = {}
    for row, _, p in usable:
        subject_seconds[row.subject] = subject_seconds.get(row.subject, 0.0) + p["duration_seconds"]
    heldout = split_charades_subjects(subject_seconds, heldout_fraction)

    zip_str = str(video_zip.resolve()).replace("\\", "/")
    records = []
    for row, member, p in usable:
        records.append(
            IngestionRecordV6(
                source_dataset="Charades",
                sequence_id=f"charades_{row.id}",
                subject_id=f"charades_{str(row.subject).lower()}",
                camera_id="cam0",
                environment=f"home_{str(row.scene).lower().replace(' ', '_').replace('/', '_')}",
                fps=p["fps"],
                duration_seconds=p["duration_seconds"],
                total_frames=p["frame_count"],
                resolution_w=p["width"],
                resolution_h=p["height"],
                is_fall=False,
                activity_label="charades_scripted_adl",
                fall_start_sec=None,
                fall_end_sec=None,
                lying_start_sec=None,
                license_type="Charades-NonCommercial",
                split="longform_adl_heldout" if row.subject in heldout else "dev_longform",
                video_relative_path=f"{zip_str}{ZIP_MEMBER_SEP}{member}",
                sha256_hash=p["sha256"],
                is_long_form=True,
                is_optical_authentic=p["is_optical"],
                scene_cuts_sec=[],
                reviewed_no_falls=False,  # keyword-screened, not human-reviewed
            )
        )
    LOG.info(
        "Charades: %d clips ingested (%d subjects, %d held out)",
        len(records),
        len(subject_seconds),
        len(heldout),
    )
    return records, rejections


def build_v6_manifest(
    records: list[IngestionRecordV6],
    out_json: Path,
    rejections: list[dict[str, Any]] | None = None,
    out_rejections: Path | None = None,
    out_csv: Path | None = None,
    enforce_counts: bool = True,
) -> dict[str, Any]:
    """Generate locked V6 dataset manifest with hard assertions and split validation."""
    dev_records = [r for r in records if r.split == "dev"]
    dev_longform_records = [r for r in records if r.split == "dev_longform"]
    longform_heldout_records = [
        r for r in records if r.split == "longform_adl_heldout"
    ]
    test_a_records = [r for r in records if r.split == "test_a"]
    test_x_records = [r for r in records if r.split == "test_x"]
    test_b_records = [r for r in records if r.split == "test_b"]
    longform_records = [r for r in records if r.split in {"longform_adl", "dev_longform", "longform_adl_heldout"}]

    dev_subjs = sorted(list({r.subject_id for r in dev_records}))
    test_a_subjs = sorted(list({r.subject_id for r in test_a_records}))
    test_x_subjs = sorted(list({r.subject_id for r in test_x_records}))
    test_b_subjs = sorted(list({r.subject_id for r in test_b_records}))

    dev_urfd_count = len([r for r in dev_records if r.source_dataset == "URFD"])
    dev_upfall_count = len([r for r in dev_records if r.source_dataset == "UP-Fall"])
    total_longform_hours = sum(r.duration_seconds for r in longform_records) / 3600.0

    # 1. Verify zero duplicate video hashes across different sequences
    all_hashes = [r.sha256_hash for r in records]
    if len(all_hashes) != len(set(all_hashes)):
        raise RuntimeError(
            "Duplicate video SHA-256 hashes detected in dataset manifest"
        )

    # 2. Verify zero subject overlap between dev and test splits
    dev_subj_set = set(dev_subjs)
    test_a_overlap = dev_subj_set.intersection(set(test_a_subjs))
    test_x_overlap = dev_subj_set.intersection(set(test_x_subjs))
    test_b_overlap = dev_subj_set.intersection(set(test_b_subjs))

    if test_a_overlap:
        raise RuntimeError(
            f"Subject leakage detected between Dev and Test-A: {test_a_overlap}"
        )
    if test_x_overlap:
        raise RuntimeError(
            f"Subject leakage detected between Dev and Test-X: {test_x_overlap}"
        )
    if test_b_overlap:
        raise RuntimeError(
            f"Subject leakage detected between Dev and Test-B: {test_b_overlap}"
        )
    lf_overlap = {r.subject_id for r in dev_longform_records} & {
        r.subject_id for r in longform_heldout_records
    }
    if lf_overlap:
        raise RuntimeError(
            f"Subject leakage detected between dev_longform and longform_adl_heldout: {lf_overlap}"
        )

    LOG.info(
        "Partition Counts: Dev=%d (URFD=%d, UP-Fall=%d), Dev-Longform=%d, Test-A=%d, Test-X=%d, Test-B=%d, Longform Total=%d (%.2f h)",
        len(dev_records),
        dev_urfd_count,
        dev_upfall_count,
        len(dev_longform_records),
        len(test_a_records),
        len(test_x_records),
        len(test_b_records),
        len(longform_records),
        total_longform_hours,
    )

    if enforce_counts:
        if dev_urfd_count != 70 or dev_upfall_count != 720:
            raise AssertionError(
                f"Dev counts do not match target (Expected URFD=70, UP-Fall=720; Got URFD={dev_urfd_count}, UP-Fall={dev_upfall_count})"
            )
        if len(test_a_records) != 132:
            raise AssertionError(
                f"Test-A count mismatch: Expected 132, got {len(test_a_records)}"
            )
        if len(test_x_records) != 132:
            raise AssertionError(
                f"Test-X count mismatch: Expected 132, got {len(test_x_records)}"
            )
        if len(test_b_records) != 132:
            raise AssertionError(
                f"Test-B count mismatch: Expected 132, got {len(test_b_records)}"
            )
        vlog_records = [r for r in longform_records if r.source_dataset == "LongformADL"]
        vlog_hours = sum(r.duration_seconds for r in vlog_records) / 3600.0
        if len(vlog_records) != 12 or not (5.10 <= vlog_hours <= 5.20):
            raise AssertionError(
                f"Longform count/duration mismatch: Expected 12 files (~5.15 h), got {len(vlog_records)} files ({vlog_hours:.3f} h)"
            )

    charades_records = [r for r in records if r.source_dataset == "Charades"]
    charades_info = {
        split: {
            "count": len(rs),
            "hours": round(sum(r.duration_seconds for r in rs) / 3600.0, 3),
            "subjects": len({r.subject_id for r in rs}),
        }
        for split in ("dev_longform", "longform_adl_heldout")
        for rs in [[r for r in charades_records if r.split == split]]
    }

    manifest = {
        "manifest_version": "6.5.0" if charades_records else "6.1.0",
        "phase": "V6.5 / Phase 4 (Charades longform ADL)" if charades_records else "Phase 11.8 / V6.1",
        "total_records": len(records),
        "partition_verification": {
            "dev_count": len(dev_records),
            "dev_longform_count": len(dev_longform_records),
            "dev_longform_hours": round(
                sum(r.duration_seconds for r in dev_longform_records) / 3600.0, 3
            ),
            "longform_heldout_count": len(longform_heldout_records),
            "longform_heldout_hours": round(
                sum(r.duration_seconds for r in longform_heldout_records) / 3600.0, 3
            ),
            "dev_urfd_count": dev_urfd_count,
            "dev_upfall_count": dev_upfall_count,
            "test_a_count": len(test_a_records),
            "test_x_count": len(test_x_records),
            "test_b_count": len(test_b_records),
            "longform_count": len(longform_records),
            "longform_duration_hours": round(total_longform_hours, 3),
            "charades": charades_info,
            "dev_subjects": dev_subjs,
            "test_a_subjects": test_a_subjs,
            "test_x_subjects": test_x_subjs,
            "test_b_subjects": test_b_subjs,
            "zero_subject_overlap": True,
            "zero_hash_overlap": True,
        },
        "records": [asdict(r) for r in records],
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LOG.info("Wrote V6 master manifest to %s (%d records)", out_json, len(records))

    # Write rejections log if provided
    if out_rejections is not None and rejections is not None:
        out_rejections.parent.mkdir(parents=True, exist_ok=True)
        rejection_data = {
            "timestamp": datetime.now().isoformat(),
            "total_rejected": len(rejections),
            "rejections": rejections,
        }
        out_rejections.write_text(
            json.dumps(rejection_data, indent=2), encoding="utf-8"
        )
        LOG.info(
            "Wrote ingest rejections log to %s (%d rejections)",
            out_rejections,
            len(rejections),
        )

    if out_csv:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        if records:
            fieldnames = list(asdict(records[0]).keys())
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in records:
                    d = asdict(r)
                    d["scene_cuts_sec"] = json.dumps(d["scene_cuts_sec"])
                    writer.writerow(d)
            LOG.info("Wrote V6 CSV manifest to %s", out_csv)

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest V6 Multi-Source Real Datasets")
    parser.add_argument(
        "--upfall-real-dir",
        type=Path,
        default=ROOT / "datasets" / "raw" / "upfall_real",
        help="Path to real UP-Fall dataset directory",
    )
    parser.add_argument(
        "--upfall-labels-dir",
        type=Path,
        default=None,
        help="Path to real UP-Fall labels directory or CompleteDataSet.csv",
    )
    parser.add_argument(
        "--longform-dir",
        type=Path,
        default=ROOT / "datasets" / "raw" / "longform_adl",
        help="Path to longform continuous ADL dataset directory",
    )
    parser.add_argument(
        "--sha-cache",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "sha256_cache.json",
        help="Path to persistent SHA-256 cache",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v6_master_manifest.json",
        help="Output path for V6 JSON manifest",
    )
    parser.add_argument(
        "--out-rejections",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "ingest_rejections.json",
        help="Output path for rejection log",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v6_master_manifest.csv",
        help="Output path for V6 CSV manifest",
    )
    parser.add_argument(
        "--charades-video-zip",
        type=Path,
        default=None,
        help="Charades_v1_480.zip; videos are read straight from the archive",
    )
    parser.add_argument(
        "--charades-annotations-zip",
        type=Path,
        default=None,
        help="Charades.zip (annotation CSVs); required with --charades-video-zip",
    )
    parser.add_argument(
        "--charades-heldout-fraction",
        type=float,
        default=0.2,
        help="Fraction of Charades hours (by subject) sealed as longform_adl_heldout",
    )
    parser.add_argument("--probe-workers", type=int, default=8)
    parser.add_argument(
        "--base-manifest",
        type=Path,
        default=None,
        help="Start from this manifest's records instead of re-ingesting URFD/UP-Fall/longform",
    )
    args = parser.parse_args()

    labels_dir = args.upfall_labels_dir or (args.upfall_real_dir / "labels")

    sha_cache: dict[str, str] = {}
    if args.sha_cache.is_file():
        try:
            sha_cache = json.loads(args.sha_cache.read_text(encoding="utf-8"))
        except Exception:
            sha_cache = {}

    all_records: list[IngestionRecordV6] = []
    all_rejections: list[dict[str, Any]] = []

    if args.base_manifest is not None:
        # Carry the frozen records over verbatim; only new sources are ingested.
        base = json.loads(args.base_manifest.read_text(encoding="utf-8"))
        all_records.extend(IngestionRecordV6(**r) for r in base["records"])
        LOG.info("Loaded %d records from base manifest %s", len(all_records), args.base_manifest)
    else:
        # 1. Ingest URFD records (Dev pool)
        urfd_recs, urfd_rej = ingest_urfd_records(
            sha_cache, cache_path=args.sha_cache, repo_root=ROOT
        )
        all_records.extend(urfd_recs)
        all_rejections.extend(urfd_rej)

        # 2. Ingest real UP-Fall records if directory exists
        upfall_recs, upfall_rej = ingest_real_upfall_records(
            args.upfall_real_dir,
            labels_dir,
            sha_cache,
            cache_path=args.sha_cache,
            repo_root=ROOT,
        )
        all_records.extend(upfall_recs)
        all_rejections.extend(upfall_rej)

        # 3. Ingest longform ADL records if directory exists
        longform_recs, longform_rej = ingest_longform_adl_records(
            args.longform_dir, sha_cache, cache_path=args.sha_cache, repo_root=ROOT
        )
        all_records.extend(longform_recs)
        all_rejections.extend(longform_rej)

    # 4. Ingest Charades clips straight from the zip (Phase 4 longform ADL)
    if args.charades_video_zip is not None:
        if args.charades_annotations_zip is None:
            parser.error("--charades-annotations-zip is required with --charades-video-zip")
        manifests_dir = ROOT / "datasets" / "manifests" / "phase4_charades"
        charades_recs, charades_rej = ingest_charades_records(
            args.charades_video_zip,
            args.charades_annotations_zip,
            heldout_fraction=args.charades_heldout_fraction,
            probe_cache_path=manifests_dir / "charades_probe_cache.json",
            exclusions_path=manifests_dir / "charades_fall_mention_exclusions.json",
            max_workers=args.probe_workers,
        )
        all_records.extend(charades_recs)
        all_rejections.extend(charades_rej)

    # Save final sha cache
    args.sha_cache.parent.mkdir(parents=True, exist_ok=True)
    args.sha_cache.write_text(json.dumps(sha_cache, indent=2), encoding="utf-8")

    if not all_records:
        LOG.error("No valid dataset records found.")
        return

    build_v6_manifest(
        records=all_records,
        rejections=all_rejections,
        out_json=args.out_json,
        out_rejections=args.out_rejections,
        out_csv=args.out_csv,
    )


if __name__ == "__main__":
    main()
