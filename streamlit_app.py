"""ElderCare Vision: camera-based fall detection demo.

Main Streamlit entrypoint: page configuration, theme injection, navigation,
and shared minimalist sidebar controls.
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
from app.core.nav import PAGES
from app.core.state import init_session_state
from app.views.benchmarks import render_benchmarks_view
from app.views.incidents import render_incidents_view
from app.views.overview import render_overview_view
from app.views.surveillance import render_surveillance_view
from app.views.telemetry import render_telemetry_view

st.set_page_config(
    page_title="ElderCare Vision · Fall Detection Demo",
    page_icon=":material/shield_person:",
    layout="wide",
    initial_sidebar_state="expanded",
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

pg = st.navigation(
    {
        "Overview & Live": [PAGES["overview"], PAGES["live"]],
        "Operations": [PAGES["incidents"]],
        "Verification": [PAGES["results"], PAGES["system"]],
    }
)

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand-box">
            <div class="sidebar-brand-title">ElderCare Vision</div>
            <div class="sidebar-brand-sub">Edge Fall Detection · YOLO26s-Pose</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(":green-badge[Engine Online] :gray-badge[v6.3 Sealed]")

pg.run()

with st.sidebar:
    st.divider()
    st.caption("**:material/lock: Local Privacy Boundary**")
    st.caption(
        "Raw video never leaves this machine. Alerts retain only 3 keyframe "
        "snapshots for human audit."
    )
