"""Atomic disk storage and provenance verification for keypoint cache files (P4-006)."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from eldercare.fall_engine.cache.schema import (
    CachedFrame,
    CachedKeypointSequence,
    CachedPerson,
    KeypointCacheMetadata,
)
from eldercare.fall_engine.cache.serialization import (
    deserialize_sequence_from_json,
    serialize_sequence_to_json,
)
from eldercare.vision.pose.adapter import Keypoint

# track_ids value marking an unused person slot in multi-person NPZ caches.
EMPTY_SLOT_TRACK_ID = -2


def save_keypoint_cache_npz(
    sequence: CachedKeypointSequence,
    target_path: str | Path,
) -> Path:
    """Save a CachedKeypointSequence as a compressed NumPy archive (.npz).

    Every person in every frame is stored (multi-person layout): ``keypoints``
    (T, P, 17, 3), ``presents`` (T, P, 17), ``bboxes`` (T, P, 4), ``confidences``
    (T, P) and ``track_ids`` (T, P), where P is the most persons seen in one frame and
    unused slots have track_id -2. A person without a tracker id is stored as -1.
    """
    dest = Path(target_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    n_frames = len(sequence.frames)
    n_slots = max([len(f.persons) for f in sequence.frames] + [1])
    kpts_arr = np.full((n_frames, n_slots, 17, 3), np.nan, dtype=np.float32)
    presents_arr = np.zeros((n_frames, n_slots, 17), dtype=bool)
    bboxes_arr = np.zeros((n_frames, n_slots, 4), dtype=np.float32)
    confidences = np.zeros((n_frames, n_slots), dtype=np.float32)
    track_ids = np.full((n_frames, n_slots), EMPTY_SLOT_TRACK_ID, dtype=np.int32)
    timestamps = np.zeros((n_frames,), dtype=np.float64)
    frame_indices = np.zeros((n_frames,), dtype=np.int32)
    dims = np.zeros((n_frames, 2), dtype=np.int32)

    for i, f in enumerate(sequence.frames):
        timestamps[i] = f.timestamp
        frame_indices[i] = f.frame_index
        dims[i] = [f.image_width, f.image_height]
        for j, p in enumerate(f.persons):
            track_ids[i, j] = p.track_id if p.track_id is not None else -1
            confidences[i, j] = p.detection_confidence
            bboxes_arr[i, j] = p.bbox_xyxy
            for k, kp in enumerate(p.keypoints):
                if kp.present and kp.x is not None and kp.y is not None:
                    kpts_arr[i, j, k, 0] = float(kp.x)
                    kpts_arr[i, j, k, 1] = float(kp.y)
                    presents_arr[i, j, k] = True
                kpts_arr[i, j, k, 2] = float(kp.confidence)

    meta_json = json.dumps(asdict_metadata(sequence.metadata))

    temp_prefix = f".tmp_{dest.name}_"
    with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=temp_prefix, delete=False, suffix=".npz") as tmp:
        temp_path = Path(tmp.name)
        try:
            np.savez_compressed(
                temp_path,
                keypoints=kpts_arr,
                presents=presents_arr,
                bboxes=bboxes_arr,
                timestamps=timestamps,
                frame_indices=frame_indices,
                confidences=confidences,
                track_ids=track_ids,
                dims=dims,
                metadata_json=np.array(meta_json),
            )
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    temp_path.replace(dest)
    return dest


def asdict_metadata(meta: KeypointCacheMetadata) -> dict[str, Any]:
    """Serialize KeypointCacheMetadata to dict."""
    return {
        "source_sample_id": meta.source_sample_id,
        "model_name": meta.model_name,
        "inference_library_version": meta.inference_library_version,
        "extraction_timestamp": meta.extraction_timestamp,
        "total_frames": meta.total_frames,
        "inference_config": meta.inference_config,
        "source_checksum": meta.source_checksum,
        "fps": meta.fps,
        "schema_version": meta.schema_version,
        "is_derived": meta.is_derived,
        "is_ground_truth": meta.is_ground_truth,
    }


def load_keypoint_cache_npz(file_path: str | Path) -> CachedKeypointSequence:
    """Load a CachedKeypointSequence from a NumPy compressed archive (.npz)."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Keypoint cache file not found: {path}")

    with np.load(path, allow_pickle=False) as data:
        kpts_arr = data["keypoints"]
        presents_arr = data["presents"] if "presents" in data else None
        bboxes_arr = data["bboxes"]
        timestamps = data["timestamps"]
        frame_indices = data["frame_indices"]
        confidences = data["confidences"]
        track_ids = data["track_ids"]
        dims = data["dims"]
        meta_json_str = str(data["metadata_json"])

    meta_dict = json.loads(meta_json_str)
    meta = KeypointCacheMetadata(**meta_dict)

    # Legacy caches hold one primary person per frame: (T, 17, 3). Promote to (T, 1, 17, 3).
    legacy = kpts_arr.ndim == 3
    if legacy:
        kpts_arr = kpts_arr[:, None]
        presents_arr = presents_arr[:, None] if presents_arr is not None else None
        bboxes_arr = bboxes_arr[:, None]
        confidences = confidences[:, None]
        track_ids = track_ids[:, None]

    frames: list[CachedFrame] = []
    for i in range(len(timestamps)):
        persons: list[CachedPerson] = []
        for j in range(kpts_arr.shape[1]):
            tid_raw = int(track_ids[i, j])
            if tid_raw == EMPTY_SLOT_TRACK_ID:
                continue
            kps_list: list[Keypoint] = []
            for k in range(17):
                cx = float(kpts_arr[i, j, k, 0])
                cy = float(kpts_arr[i, j, k, 1])
                conf = float(kpts_arr[i, j, k, 2])
                if np.isnan(conf) or np.isinf(conf):
                    conf = 0.0
                is_present = not (np.isnan(cx) or np.isnan(cy))
                if presents_arr is not None:
                    is_present = bool(presents_arr[i, j, k]) and is_present
                if is_present:
                    kps_list.append(Keypoint(x=cx, y=cy, confidence=conf, present=True))
                else:
                    kps_list.append(Keypoint(x=None, y=None, confidence=conf, present=False))

            conf = float(confidences[i, j])
            # Legacy empty frames were stored as zero confidence with no keypoints.
            if legacy and not (conf > 0.0 or any(kp.present for kp in kps_list)):
                continue
            persons.append(
                CachedPerson(
                    track_id=tid_raw if tid_raw >= 0 else None,
                    bbox_xyxy=tuple(float(v) for v in bboxes_arr[i, j]),
                    detection_confidence=conf,
                    keypoints=tuple(kps_list),
                )
            )

        w = int(dims[i, 0]) if dims[i, 0] > 0 else 640
        h = int(dims[i, 1]) if dims[i, 1] > 0 else 480

        frames.append(
            CachedFrame(
                frame_index=int(frame_indices[i]),
                timestamp=float(timestamps[i]),
                image_width=w,
                image_height=h,
                persons=tuple(persons),
            )
        )

    return CachedKeypointSequence(metadata=meta, frames=tuple(frames))


def save_keypoint_cache(
    sequence: CachedKeypointSequence,
    target_path: str | Path,
    *,
    compress: bool = False,
    indent: int | None = 2,
) -> Path:
    """Save a CachedKeypointSequence to disk with atomic write semantics.

    If target_path ends with '.npz', writes an NPZ numpy archive.
    If target_path ends with '.gz' or compress=True, writes a gzip-compressed JSON file.
    """
    if not isinstance(sequence, CachedKeypointSequence):
        raise TypeError(f"sequence must be a CachedKeypointSequence, got {type(sequence).__name__}")

    dest = Path(target_path).resolve()
    if dest.suffix.lower() == ".npz":
        return save_keypoint_cache_npz(sequence, dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    is_gz = compress or dest.suffix.lower() == ".gz"
    json_data = serialize_sequence_to_json(sequence, indent=indent)

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

    temp_path.replace(dest)
    return dest


def load_keypoint_cache(file_path: str | Path) -> CachedKeypointSequence:
    """Load and validate a CachedKeypointSequence from disk (.json, .gz, or .npz)."""
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Keypoint cache file not found: {path}")

    if path.suffix.lower() == ".npz":
        return load_keypoint_cache_npz(path)

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
