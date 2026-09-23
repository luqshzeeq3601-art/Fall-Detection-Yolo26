"""Domain state representations and event contracts for the fall state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from eldercare.fall_engine.features.motion import TemporalFeatures


class FallState(str, Enum):
    """Lifecycle states of a tracked person in the fall detection state machine."""

    NORMAL = "NORMAL"
    DESCENT_CANDIDATE = "DESCENT_CANDIDATE"
    DOWN_CONFIRMING = "DOWN_CONFIRMING"
    FALL_CONFIRMED = "FALL_CONFIRMED"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class FallStateTransition:
    """Record of a single state machine transition for a tracked person."""

    from_state: FallState
    to_state: FallState
    timestamp: float
    reason: str
    features_snapshot: TemporalFeatures | None = None


@dataclass(frozen=True)
class FallEvent:
    """Structured event emitted when a fall is confirmed."""

    camera_id: str
    track_id: int
    confirmed_timestamp: float
    candidate_timestamp: float
    down_start_timestamp: float
    features: TemporalFeatures
    confidence: float = 1.0
    reason: str = "Down posture sustained after rapid descent"
    metadata: dict[str, str | float | int] = field(default_factory=dict)
