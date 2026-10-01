"""UI Card and Banner Components for ElderCare Vision (Light Theme)."""

from __future__ import annotations

import streamlit as st


def render_header(
    title: str,
    subtitle: str,
    status_text: str = "SYSTEM ACTIVE",
    status_variant: str = "safe",
) -> None:
    """Render top page header with high-contrast badge."""
    badge_class = f"badge-{status_variant}"
    st.markdown(
        f"""
        <div class="header-container">
            <div>
                <h1 class="header-title">{title}</h1>
                <div class="header-subtitle">{subtitle}</div>
            </div>
            <div>
                <span class="status-badge {badge_class}">
                    ● {status_text}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_demo_tour_guide(
    page_title: str,
    steps: list[str],
) -> None:
    """Render a clean, collapsible presentation guide for interviewers/judges."""
    if not st.session_state.get("demo_tour_open", True):
        return

    with st.container(border=True):
        col_text, col_btn = st.columns([0.92, 0.08])
        with col_text:
            st.markdown(
                f":material/lightbulb: **Presentation Guide — {page_title}**\n\n"
                + "\n".join(f"- {step}" for step in steps)
            )
        with col_btn:
            if st.button(":material/close:", key=f"dismiss_tour_{page_title}", help="Dismiss guide"):
                st.session_state.demo_tour_open = False
                st.rerun()


def render_fall_alert_banner(
    camera_name: str,
    time_str: str,
    confidence: float,
    tta_seconds: float = 1.8,
) -> None:
    """Render an unmistakable emergency fall alarm card."""
    conf_pct = int(confidence * 100)
    st.markdown(
        f"""
        <div class="fall-alert-banner">
            <div>
                <div class="fall-alert-title">
                    🚨 CRITICAL ALERT — FALL DETECTED
                </div>
                <div class="fall-alert-detail">
                    <strong>Location:</strong> {camera_name} &nbsp;|&nbsp;
                    <strong>Timestamp:</strong> {time_str} &nbsp;|&nbsp;
                    <strong>Time-to-Alert:</strong> {tta_seconds:.1f}s
                </div>
            </div>
            <div>
                <span class="status-badge badge-alarm" style="font-size: 0.9rem; padding: 0.4rem 0.9rem;">
                    CONFIDENCE {conf_pct}%
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
