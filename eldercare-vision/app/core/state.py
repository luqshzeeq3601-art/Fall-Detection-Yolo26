"""Session state management for ElderCare Vision Streamlit App."""

from __future__ import annotations

import streamlit as st

from app.core.data_loader import get_default_incidents


def init_session_state() -> None:
    """Initialize all required session state variables with clean defaults."""
    if "incidents" not in st.session_state:
        st.session_state.incidents = get_default_incidents()

    if "demo_tour_open" not in st.session_state:
        st.session_state.demo_tour_open = True

    if "active_video_index" not in st.session_state:
        st.session_state.active_video_index = 0

    if "show_skeletons" not in st.session_state:
        st.session_state.show_skeletons = True

    if "show_bbox" not in st.session_state:
        st.session_state.show_bbox = True

    if "privacy_blur" not in st.session_state:
        st.session_state.privacy_blur = False

    # Defaults come from the frozen V6.3 operating point (models/v6_3_phase3b).
    if "fall_threshold" not in st.session_state or "down_sustain_sec" not in st.session_state:
        from app.core.inference_runner import frozen_operating_point

        op = frozen_operating_point()
        st.session_state.setdefault("fall_threshold", op.get("fall_trigger_threshold", 0.55))
        st.session_state.setdefault("down_sustain_sec", op.get("min_down_sustain_seconds", 0.45))

    if "live_alerts_triggered" not in st.session_state:
        st.session_state.live_alerts_triggered = 0

    if "simulated_falls" not in st.session_state:
        st.session_state.simulated_falls = []
