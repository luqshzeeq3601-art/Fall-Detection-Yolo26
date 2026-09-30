"""Online tracklet stitching for tracker ID fragmentation during falls.

Stock ByteTrack often assigns a new ID when a person falls (fast pose and bbox change
breaks IoU association). The stitcher maps raw tracker IDs to stable IDs: a newly
appearing raw ID inherits the stable ID of a recently lost track whose last bbox
centre is close. It only uses past frames, so the same logic runs live and offline,
and training windows and inference observations see identical tracks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]


@dataclass
class OnlineTrackStitcher:
    """Map raw tracker IDs to stable IDs, frame by frame, in timestamp order.

    Args:
        max_gap_sec: A lost track can be continued only within this many seconds.
        max_dist_heights: Max centre distance, in multiples of the lost track's last
            bbox height, for a new raw ID to continue it.
    """

    max_gap_sec: float = 1.0
    max_dist_heights: float = 1.5
    _stable_of: dict[int, int] = field(default_factory=dict)
    _last: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)

    def reset(self) -> None:
        self._stable_of.clear()
        self._last.clear()

    def update(self, timestamp: float, detections: list[tuple[int, BBox]]) -> list[int]:
        """Return the stable ID for each (raw_id, bbox) detection of one frame."""
        stable_ids: list[int | None] = [None] * len(detections)
        claimed: set[int] = set()

        # Known raw IDs keep their stable ID.
        for i, (raw_id, _) in enumerate(detections):
            if raw_id in self._stable_of:
                stable_ids[i] = self._stable_of[raw_id]
                claimed.add(self._stable_of[raw_id])

        # New raw IDs may continue the nearest recently lost track.
        for i, (raw_id, bbox) in enumerate(detections):
            if stable_ids[i] is not None:
                continue
            cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
            best, best_dist = None, math.inf
            for sid, (t_last, lx, ly, lh) in self._last.items():
                if sid in claimed or not (0.0 < timestamp - t_last <= self.max_gap_sec):
                    continue
                dist = math.hypot(cx - lx, cy - ly)
                if dist <= self.max_dist_heights * max(lh, 1.0) and dist < best_dist:
                    best, best_dist = sid, dist
            sid = best if best is not None else raw_id
            self._stable_of[raw_id] = sid
            stable_ids[i] = sid
            claimed.add(sid)

        for (_, bbox), sid in zip(detections, stable_ids, strict=True):
            assert sid is not None
            self._last[sid] = (
                timestamp,
                (bbox[0] + bbox[2]) / 2.0,
                (bbox[1] + bbox[3]) / 2.0,
                bbox[3] - bbox[1],
            )
        return [sid for sid in stable_ids if sid is not None]
