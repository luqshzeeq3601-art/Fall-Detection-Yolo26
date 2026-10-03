"""Streamlit wrappers around the shared fall inference engine (``eldercare.live.engine``)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.live import engine as _engine
from eldercare.live.engine import (
    FROZEN_MODEL_DIR,
    FallInferenceEngine,
    FrameInferenceResult,
    frozen_operating_point,
)

__all__ = [
    "FROZEN_MODEL_DIR",
    "FallInferenceEngine",
    "FrameInferenceResult",
    "frozen_operating_point",
    "load_frozen_fall_model",
    "load_pose_model",
]


@st.cache_resource(show_spinner="Loading YOLO26s-Pose Model...")
def load_pose_model() -> Any | None:
    """Load Ultralytics YOLO26s-Pose model with caching."""
    return _engine.load_pose_model()


@st.cache_resource(show_spinner="Loading frozen V6.3 fall classifier...")
def load_frozen_fall_model() -> tuple[TemporalSkeletonClassifierV5, dict[str, Any]] | None:
    """Frozen M2 classifier and its calibrated operating point, or None if missing."""
    return _engine.load_frozen_fall_model()
