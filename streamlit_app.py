"""ElderCare Vision: camera-based fall detection demo.

Main Streamlit entrypoint: page configuration, theme injection, and the shared
sidebar (brand, engine status, grouped navigation, privacy note).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root and src are on sys.path
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

from app.components.theme import apply_custom_theme
from app.core.inference_runner import FROZEN_MODEL_DIR
from app.core.nav import PAGES
from app.core.state import init_session_state
from app.views.benchmarks import render_benchmarks_view
from app.views.incidents import render_incidents_view
from app.views.overview import render_overview_view
from app.views.surveillance import render_surveillance_view
from app.views.telemetry import render_telemetry_view
from eldercare.live.engine import pose_weights_path

st.set_page_config(
    page_title="ElderCare Vision · Fall Detection Demo",
    page_icon=":material/shield_person:",
    layout="wide",
    initial_sidebar_state="auto",
)

init_session_state()
apply_custom_theme()

PAGES.update(
    {
        "overview": st.Page(
            render_overview_view,
            title="Overview",
            icon=":material/home:",
            default=True,
        ),
        "live": st.Page(
            render_surveillance_view,
            title="Live Demo",
            icon=":material/videocam:",
            url_path="live-demo",
        ),
        "incidents": st.Page(
            render_incidents_view,
            title="Incidents & Review",
            icon=":material/fact_check:",
            url_path="incidents",
        ),
        "results": st.Page(
            render_benchmarks_view,
            title="Benchmarks & Gate",
            icon=":material/analytics:",
            url_path="results",
        ),
        "system": st.Page(
            render_telemetry_view,
            title="System Telemetry",
            icon=":material/monitor_heart:",
            url_path="system",
        ),
    }
)

NAV_GROUPS: dict[str, list[str]] = {
    "Monitor": ["overview", "live"],
    "Review": ["incidents"],
    "Evidence": ["results", "system"],
}

# Sidebar nav is drawn below so the brand and status sit above it.
pg = st.navigation([PAGES[k] for keys in NAV_GROUPS.values() for k in keys], position="hidden")

# Cheap file checks; the models themselves load lazily on the Live Demo page.
engine_ready = (
    pose_weights_path() is not None
    and (FROZEN_MODEL_DIR / "temporal_skeleton_classifier_v6.pt").is_file()
)

st.logo(":material/shield_person:", size="large")

with st.sidebar:
    st.html(
        """
        <div class="sidebar-brand">
            <span class="sidebar-brand__title">ElderCare Vision</span>
            <span class="sidebar-brand__sub">Fall detection on local video</span>
        </div>
        """
    )
    with st.container(horizontal=True, gap="small"):
        if engine_ready:
            st.badge("Engine ready", color="green", icon=":material/check_circle:")
        else:
            st.badge("Weights missing", color="orange", icon=":material/warning:")
        st.badge("Model v6.3", color="gray")

    for group, keys in NAV_GROUPS.items():
        st.html(f'<div class="sidebar-group">{group}</div>')
        for key in keys:
            st.page_link(PAGES[key])

pg.run()

with st.sidebar:
    st.divider()
    st.caption(":material/lock: **Raw video never leaves this machine.**")
    st.caption("Each alert keeps only 3 snapshots for caregiver review.")
