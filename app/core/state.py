"""Session state management for ElderCare Vision Streamlit App."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    """Initialize all required session state variables with clean defaults."""
    st.session_state.setdefault("show_skeletons", True)
    st.session_state.setdefault("show_bbox", True)
    st.session_state.setdefault("privacy_blur", False)
    st.session_state.setdefault("alerts_this_session", 0)
    st.session_state.setdefault("last_incident_id", None)

    # Defaults come from the frozen V6.3 operating point (models/v6_3_phase3b).
    if "fall_threshold" not in st.session_state or "down_sustain_sec" not in st.session_state:
        from app.core.inference_runner import frozen_operating_point

        op = frozen_operating_point()
        st.session_state.setdefault("fall_threshold", op.get("fall_trigger_threshold", 0.55))
        st.session_state.setdefault("down_sustain_sec", op.get("min_down_sustain_seconds", 0.45))
