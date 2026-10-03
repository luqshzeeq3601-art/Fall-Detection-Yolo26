"""Shared page-level building blocks and minimalist card components for ElderCare Vision."""

from __future__ import annotations

import html

import streamlit as st


def render_page_header(
    title: str,
    intro: str,
    eyebrow: str | None = None,
    badge_text: str | None = None,
    badge_color: str = "blue",
) -> None:
    """Render a minimalist page header with optional eyebrow category and lead text."""
    if eyebrow:
        st.markdown(
            f'<div class="page-eyebrow">{html.escape(eyebrow)}</div>',
            unsafe_allow_html=True,
        )

    if badge_text:
        col_t, col_b = st.columns([0.8, 0.2], vertical_alignment="center")
        with col_t:
            st.title(title)
        with col_b:
            st.badge(badge_text, color=badge_color)
    else:
        st.title(title)

    st.markdown(f'<p class="page-intro">{html.escape(intro)}</p>', unsafe_allow_html=True)


def render_section_header(
    title: str,
    subtitle: str | None = None,
    icon: str | None = None,
) -> None:
    """Render a clean, low-clutter section header with optional subtitle."""
    heading = f"{icon} {title}" if icon else title
    st.subheader(heading)
    if subtitle:
        st.caption(subtitle)


# Detection state -> (label shown to people, badge color, icon)
# Text and icon carry the meaning, preserving accessibility and clear state transitions.
STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    "IDLE": ("Ready: standby", "gray", ":material/pause_circle:"),
    "NORMAL": ("Monitoring: normal activity", "green", ":material/check_circle:"),
    "NO_PERSON": ("Searching: no person in frame", "gray", ":material/visibility:"),
    "FALLING": ("Candidate fall: confirming posture", "orange", ":material/warning:"),
    "FALL_DETECTED": ("FALL DETECTED: alert dispatched", "red", ":material/emergency:"),
}


def render_status_badge(state: str) -> None:
    """Render a high-contrast, accessible status badge for the detector state."""
    label, color, icon = STATUS_STYLES.get(state, STATUS_STYLES["IDLE"])
    st.badge(label, color=color, icon=icon)


def render_live_indicator(label: str = "Edge Camera Active", active: bool = True) -> None:
    """Render a sleek live pulse dot indicator."""
    dot_class = "live-dot" if active else ""
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem;">
            <span class="{dot_class}" style="background-color: {"#16a34a" if active else "#71717a"};"></span>
            <span style="font-size: 0.8rem; font-weight: 500; opacity: 0.8;">{html.escape(label)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
