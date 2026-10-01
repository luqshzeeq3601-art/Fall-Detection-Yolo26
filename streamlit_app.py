"""ElderCare Vision: camera-based fall detection demo.

Main Streamlit entrypoint: page config, navigation and shared sidebar.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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
    page_title="ElderCare Vision · Fall detection demo",
    page_icon=":material/shield_person:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
apply_custom_theme()

PAGES.update(
    {
        "overview": st.Page(
            render_overview_view, title="Overview", icon=":material/home:", default=True
        ),
        "live": st.Page(
            render_surveillance_view,
            title="Live demo",
            icon=":material/videocam:",
            url_path="live-demo",
        ),
        "incidents": st.Page(
            render_incidents_view,
            title="Incidents & review",
            icon=":material/fact_check:",
            url_path="incidents",
        ),
        "results": st.Page(
            render_benchmarks_view,
            title="Results",
            icon=":material/analytics:",
            url_path="results",
        ),
        "system": st.Page(
            render_telemetry_view,
            title="System status",
            icon=":material/monitor_heart:",
            url_path="system",
        ),
    }
)

pg = st.navigation(
    {
        "Explore": [PAGES["overview"], PAGES["live"]],
        "Review": [PAGES["incidents"]],
        "Evidence": [PAGES["results"], PAGES["system"]],
    }
)

with st.sidebar:
    st.markdown("**ElderCare Vision**")
    st.caption("Fall detection research prototype")

pg.run()

with st.sidebar:
    st.divider()
    st.caption("Frozen model V6.3 · YOLO26s-Pose · runs locally")
