"""ElderCare Vision ByteTrack tracking boundary (P3-001)."""

from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import (
    TrackObservation,
    tracked_frame_to_observations,
)
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
    "TrackHistory",
    "TrackHistoryConfig",
    "TrackObservation",
    "TrackedFrame",
    "TrackedPerson",
    "UltralyticsByteTrackBackend",
    "associate_detections_to_tracks",
    "bbox_iou",
    "tracked_frame_to_observations",
]
