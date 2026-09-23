"""JSON serialization and domain conversion for derived keypoint cache (P4-006)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from eldercare.fall_engine.cache.schema import (
    CachedFrame,
    CachedKeypointSequence,
    CachedPerson,
    KeypointCacheMetadata,
)
from eldercare.vision.pose.adapter import Keypoint, PersonPose
from eldercare.vision.tracking.observation import TrackObservation
from eldercare.vision.tracking.tracker import TrackedFrame, TrackedPerson


def keypoint_to_dict(kp: Keypoint) -> dict[str, Any]:
    """Serialize Keypoint to dictionary."""
    return {
        "x": kp.x,
        "y": kp.y,
        "confidence": kp.confidence,
        "present": kp.present,
    }


def keypoint_from_dict(data: dict[str, Any]) -> Keypoint:
    """Deserialize Keypoint from dictionary."""
    if not isinstance(data, dict):
        raise TypeError(f"keypoint data must be a dict, got {type(data).__name__}")
    return Keypoint(
        x=data.get("x"),
        y=data.get("y"),
        confidence=data.get("confidence", 0.0),
        present=data.get("present", False),
    )


def cached_person_to_dict(person: CachedPerson) -> dict[str, Any]:
    """Serialize CachedPerson to dictionary."""
    return {
        "track_id": person.track_id,
        "bbox_xyxy": list(person.bbox_xyxy),
        "detection_confidence": person.detection_confidence,
        "keypoints": [keypoint_to_dict(kp) for kp in person.keypoints],
    }


def cached_person_from_dict(data: dict[str, Any]) -> CachedPerson:
    """Deserialize CachedPerson from dictionary."""
    if not isinstance(data, dict):
        raise TypeError(f"person data must be a dict, got {type(data).__name__}")
    kps_raw = data.get("keypoints", [])
    if not isinstance(kps_raw, (list, tuple)):
        raise TypeError("keypoints in person data must be a list")
    keypoints = tuple(keypoint_from_dict(kp) for kp in kps_raw)
    bbox_raw = data.get("bbox_xyxy", [])
    if not isinstance(bbox_raw, (list, tuple)) or len(bbox_raw) != 4:
        raise ValueError("bbox_xyxy in person data must be 4 coordinates")
    bbox = (float(bbox_raw[0]), float(bbox_raw[1]), float(bbox_raw[2]), float(bbox_raw[3]))
    return CachedPerson(
        track_id=data.get("track_id"),
        bbox_xyxy=bbox,
        detection_confidence=float(data.get("detection_confidence", 0.0)),
        keypoints=keypoints,
    )


def cached_frame_to_dict(frame: CachedFrame) -> dict[str, Any]:
    """Serialize CachedFrame to dictionary."""
    return {
        "frame_index": frame.frame_index,
        "timestamp": frame.timestamp,
        "image_width": frame.image_width,
        "image_height": frame.image_height,
        "persons": [cached_person_to_dict(p) for p in frame.persons],
    }


def cached_frame_from_dict(data: dict[str, Any]) -> CachedFrame:
    """Deserialize CachedFrame from dictionary."""
    if not isinstance(data, dict):
        raise TypeError(f"frame data must be a dict, got {type(data).__name__}")
    persons_raw = data.get("persons", [])
    if not isinstance(persons_raw, (list, tuple)):
        raise TypeError("persons in frame data must be a list")
    persons = tuple(cached_person_from_dict(p) for p in persons_raw)
    return CachedFrame(
        frame_index=int(data.get("frame_index", 0)),
        timestamp=float(data.get("timestamp", 0.0)),
        image_width=int(data.get("image_width", 0)),
        image_height=int(data.get("image_height", 0)),
        persons=persons,
    )


def metadata_to_dict(meta: KeypointCacheMetadata) -> dict[str, Any]:
    """Serialize KeypointCacheMetadata to dictionary."""
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


def metadata_from_dict(data: dict[str, Any]) -> KeypointCacheMetadata:
    """Deserialize KeypointCacheMetadata from dictionary."""
    if not isinstance(data, dict):
        raise TypeError(f"metadata must be a dict, got {type(data).__name__}")
    return KeypointCacheMetadata(
        source_sample_id=str(data.get("source_sample_id", "")),
        model_name=str(data.get("model_name", "")),
        inference_library_version=str(data.get("inference_library_version", "")),
        extraction_timestamp=str(data.get("extraction_timestamp", "")),
        total_frames=int(data.get("total_frames", 0)),
        inference_config=data.get("inference_config", {}),
        source_checksum=data.get("source_checksum"),
        fps=data.get("fps"),
        schema_version=str(data.get("schema_version", "1.0")),
        is_derived=bool(data.get("is_derived", True)),
        is_ground_truth=bool(data.get("is_ground_truth", False)),
    )


def sequence_to_dict(sequence: CachedKeypointSequence) -> dict[str, Any]:
    """Convert a CachedKeypointSequence to a nested dictionary representation."""
    return {
        "metadata": metadata_to_dict(sequence.metadata),
        "frames": [cached_frame_to_dict(f) for f in sequence.frames],
    }


def sequence_from_dict(data: dict[str, Any]) -> CachedKeypointSequence:
    """Convert a nested dictionary to a CachedKeypointSequence."""
    if not isinstance(data, dict):
        raise TypeError(f"sequence data must be a dict, got {type(data).__name__}")
    if "metadata" not in data or "frames" not in data:
        raise ValueError("sequence data must contain 'metadata' and 'frames' keys")
    metadata = metadata_from_dict(data["metadata"])
    frames_raw = data["frames"]
    if not isinstance(frames_raw, (list, tuple)):
        raise TypeError("frames must be a list of frame objects")
    frames = tuple(cached_frame_from_dict(f) for f in frames_raw)
    return CachedKeypointSequence(metadata=metadata, frames=frames)


def serialize_sequence_to_json(sequence: CachedKeypointSequence, *, indent: int | None = 2) -> str:
    """Serialize a CachedKeypointSequence to a JSON formatted string."""
    data = sequence_to_dict(sequence)
    return json.dumps(data, indent=indent)


def deserialize_sequence_from_json(json_str: str) -> CachedKeypointSequence:
    """Deserialize a CachedKeypointSequence from a JSON formatted string."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON string for keypoint sequence: {exc}") from exc
    return sequence_from_dict(data)


# ---------------------------------------------------------------------------
# Bidirectional Domain Conversion
# ---------------------------------------------------------------------------


def sequence_from_tracked_frames(
    metadata: KeypointCacheMetadata,
    frames: Sequence[tuple[float, TrackedFrame]],
) -> CachedKeypointSequence:
    """Convert a sequence of (timestamp, TrackedFrame) tuples to a CachedKeypointSequence."""
    cached_frames: list[CachedFrame] = []
    for idx, (timestamp, frame) in enumerate(frames):
        if not isinstance(frame, TrackedFrame):
            raise TypeError(
                f"frame {idx} must be a TrackedFrame instance, got {type(frame).__name__}"
            )
        persons: list[CachedPerson] = []
        for tp in frame.persons:
            p_pose = tp.person
            cached_p = CachedPerson(
                track_id=tp.track_id,
                bbox_xyxy=p_pose.bbox_xyxy,
                detection_confidence=p_pose.detection_confidence,
                keypoints=p_pose.keypoints,
            )
            persons.append(cached_p)
        cached_frames.append(
            CachedFrame(
                frame_index=idx,
                timestamp=float(timestamp),
                image_width=frame.image_width,
                image_height=frame.image_height,
                persons=tuple(persons),
            )
        )
    return CachedKeypointSequence(metadata=metadata, frames=tuple(cached_frames))


def sequence_to_tracked_frames(
    sequence: CachedKeypointSequence,
) -> tuple[tuple[float, TrackedFrame], ...]:
    """Convert a CachedKeypointSequence back to a tuple of (timestamp, TrackedFrame) tuples."""
    result: list[tuple[float, TrackedFrame]] = []
    for f in sequence.frames:
        tracked_persons: list[TrackedPerson] = []
        for p in f.persons:
            pose = PersonPose(
                bbox_xyxy=p.bbox_xyxy,
                detection_confidence=p.detection_confidence,
                keypoints=p.keypoints,
            )
            tracked_persons.append(TrackedPerson(person=pose, track_id=p.track_id))
        frame = TrackedFrame(
            image_width=f.image_width,
            image_height=f.image_height,
            persons=tuple(tracked_persons),
        )
        result.append((f.timestamp, frame))
    return tuple(result)


def sequence_to_observations(
    sequence: CachedKeypointSequence,
    *,
    camera_id: str = "cached_cam",
) -> tuple[TrackObservation, ...]:
    """Convert a CachedKeypointSequence into a flat tuple of TrackObservation instances."""
    observations: list[TrackObservation] = []
    for f in sequence.frames:
        for p in f.persons:
            obs = TrackObservation(
                camera_id=camera_id,
                track_id=p.track_id,
                timestamp=f.timestamp,
                bbox_xyxy=p.bbox_xyxy,
                detection_confidence=p.detection_confidence,
                keypoints=p.keypoints,
                image_width=f.image_width,
                image_height=f.image_height,
            )
            observations.append(obs)
    return tuple(observations)


def sequence_from_observations(
    metadata: KeypointCacheMetadata,
    observations: Sequence[TrackObservation],
) -> CachedKeypointSequence:
    """Group flat TrackObservation stream by timestamp and build CachedKeypointSequence."""
    from collections import defaultdict

    frames_by_ts: dict[float, list[TrackObservation]] = defaultdict(list)
    for obs in observations:
        if not isinstance(obs, TrackObservation):
            raise TypeError(f"observation must be a TrackObservation, got {type(obs).__name__}")
        frames_by_ts[obs.timestamp].append(obs)

    sorted_timestamps = sorted(frames_by_ts.keys())
    cached_frames: list[CachedFrame] = []
    for idx, ts in enumerate(sorted_timestamps):
        obs_group = frames_by_ts[ts]
        first = obs_group[0]
        persons = tuple(
            CachedPerson(
                track_id=o.track_id,
                bbox_xyxy=o.bbox_xyxy,
                detection_confidence=o.detection_confidence,
                keypoints=o.keypoints,
            )
            for o in obs_group
        )
        cached_frames.append(
            CachedFrame(
                frame_index=idx,
                timestamp=ts,
                image_width=first.image_width,
                image_height=first.image_height,
                persons=persons,
            )
        )
    return CachedKeypointSequence(metadata=metadata, frames=tuple(cached_frames))
