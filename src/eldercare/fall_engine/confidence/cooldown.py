"""Incident cooldown management to prevent duplicate alert storms (P4-004)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CooldownConfig:
    """Configuration for fall incident alert throttling."""

    # Time in seconds that must elapse before the same track can emit another fall alert
    incident_cooldown_sec: float = 5.0

    # Minimum spacing in seconds between any alerts on the same camera
    camera_cooldown_sec: float = 0.5


class IncidentCooldownManager:
    """Tracks incident alert history and determines whether a track or camera is in cooldown."""

    def __init__(self, config: CooldownConfig | None = None) -> None:
        self.config = config or CooldownConfig()
        self._track_cooldowns: dict[tuple[str, int], float] = {}
        self._camera_cooldowns: dict[str, float] = {}

    def is_in_cooldown(self, camera_id: str, track_id: int, timestamp: float) -> bool:
        """Check if an alert for this track or camera is currently suppressed by cooldown.

        Args:
            camera_id: Camera identifier.
            track_id: Person track identifier.
            timestamp: Current observation timestamp.

        Returns:
            True if within cooldown window, False otherwise.
        """
        # Check per-track cooldown
        track_key = (camera_id, track_id)
        last_track_time = self._track_cooldowns.get(track_key)
        if last_track_time is not None:
            if (timestamp - last_track_time) < self.config.incident_cooldown_sec:
                return True

        # Check per-camera cooldown
        last_cam_time = self._camera_cooldowns.get(camera_id)
        if last_cam_time is not None:
            if (timestamp - last_cam_time) < self.config.camera_cooldown_sec:
                return True

        return False

    def record_incident(self, camera_id: str, track_id: int, timestamp: float) -> None:
        """Record an emitted incident timestamp for cooldown tracking."""
        track_key = (camera_id, track_id)
        self._track_cooldowns[track_key] = timestamp
        self._camera_cooldowns[camera_id] = timestamp
        logger.debug(
            "Incident recorded for track (%s, %d) at timestamp %.3fs",
            camera_id,
            track_id,
            timestamp,
        )

    def cleanup_expired(self, current_timestamp: float, max_idle_sec: float = 60.0) -> int:
        """Remove tracked cooldown entries that have aged past max_idle_sec.

        Args:
            current_timestamp: Current time in seconds.
            max_idle_sec: Maximum age in seconds before purging a record.

        Returns:
            Number of purged track cooldown entries.
        """
        expired_tracks = [
            k for k, t in self._track_cooldowns.items() if (current_timestamp - t) > max_idle_sec
        ]
        for k in expired_tracks:
            del self._track_cooldowns[k]

        expired_cameras = [
            k for k, t in self._camera_cooldowns.items() if (current_timestamp - t) > max_idle_sec
        ]
        for k in expired_cameras:
            del self._camera_cooldowns[k]

        return len(expired_tracks)

    def reset(self) -> None:
        """Reset all cooldown history."""
        self._track_cooldowns.clear()
        self._camera_cooldowns.clear()
