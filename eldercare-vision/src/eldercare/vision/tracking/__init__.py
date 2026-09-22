"""ElderCare Vision ByteTrack tracking boundary (P3-001)."""

from eldercare.vision.tracking.tracker import (
    ByteTrackConfig,
    PoseTracker,
    TrackBackend,
    TrackedFrame,
    TrackedPerson,
    UltralyticsByteTrackBackend,
    associate_detections_to_tracks,
    bbox_iou,
)

__all__ = [
    "ByteTrackConfig",
    "PoseTracker",
    "TrackBackend",
    "TrackedFrame",
    "TrackedPerson",
    "UltralyticsByteTrackBackend",
    "associate_detections_to_tracks",
    "bbox_iou",
]
