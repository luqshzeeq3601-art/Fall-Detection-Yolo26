"""ElderCare Vision — Edge AI Fall Detection & Intelligent Video Analytics Platform.

Main Streamlit Application Entrypoint.
Adheres to:
- developing-with-streamlit: Canonical root entrypoint, st.navigation, page routing, caching, light theme
- frontend-ui-engineering: Clinical light aesthetic, accessible contrast, purposeful cards
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
from app.core.state import init_session_state
from app.views.benchmarks import render_benchmarks_view
from app.views.incidents import render_incidents_view
from app.views.surveillance import render_surveillance_view
from app.views.telemetry import render_telemetry_view

# Page configuration
st.set_page_config(
    page_title="ElderCare Vision | Edge AI Fall Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State & Light Theme
init_session_state()
apply_custom_theme()

# Navigation Configuration using Modern st.navigation
surveillance_page = st.Page(
    render_surveillance_view,
    title="Live Surveillance",
    icon=":material/videocam:",
    default=True,
)

incidents_page = st.Page(
    render_incidents_view,
    title=f"Incident Review ({len([i for i in st.session_state.incidents if i.status == 'PENDING_REVIEW'])})",
    icon=":material/emergency:",
)

benchmarks_page = st.Page(
    render_benchmarks_view,
    title="Model Benchmarks",
    icon=":material/analytics:",
)

telemetry_page = st.Page(
    render_telemetry_view,
    title="System Telemetry",
    icon=":material/monitor_heart:",
)

# App Navigation
pg = st.navigation(
    {
        "Surveillance & Operations": [surveillance_page, incidents_page],
        "Intelligence & Observability": [benchmarks_page, telemetry_page],
    }
)

# Sidebar Header Branding
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0.5rem 0; margin-bottom: 0.75rem;">
            <div style="font-weight: 800; font-size: 1.1rem; color: #0F172A; display: flex; align-items: center; gap: 0.4rem;">
                🛡️ ElderCare Vision
            </div>
            <div style="font-size: 0.75rem; color: #64748B; font-weight: 500;">
                Edge AI Fall Detection Platform
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Run Selected Page
pg.run()

# Sidebar Footer
with st.sidebar:
    st.divider()
    st.markdown(
        """
        <div style="font-size: 0.7rem; color: #94A3B8; text-align: center;">
            ElderCare Vision v0.1.0 • Phase 11.8<br>
            YOLO26-Pose + V6.1 Kinetic Engine
        </div>
        """,
        unsafe_allow_html=True,
    )
