"""Shared page-level building blocks and minimalist card components for ElderCare Vision."""

from __future__ import annotations

import html

import streamlit as st


def render_page_header(
    title: str,
    intro: str,
    badge_text: str | None = None,
    badge_color: str = "blue",
    badge_icon: str | None = None,
) -> None:
    """Render the page title with an inline status badge and a short lead paragraph."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.title(title, width="content")
        if badge_text:
            st.badge(badge_text, color=badge_color, icon=badge_icon)

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
    "IDLE": ("Not running", "gray", ":material/pause_circle:"),
    "NORMAL": ("Normal activity", "green", ":material/check_circle:"),
    "NO_PERSON": ("No person in view", "gray", ":material/visibility:"),
    "FALLING": ("Possible fall, checking", "orange", ":material/warning:"),
    "FALL_DETECTED": ("Fall detected, alert sent", "red", ":material/emergency:"),
}


def render_status_badge(state: str) -> None:
    """Render a high-contrast, accessible status badge for the detector state."""
    label, color, icon = STATUS_STYLES.get(state, STATUS_STYLES["IDLE"])
    st.badge(label, color=color, icon=icon)


def render_live_indicator(label: str, active: bool = True) -> None:
    """Render a pipeline state label with a status dot (pulses only while running)."""
    state = "live-indicator--on" if active else ""
    st.markdown(
        f'<span class="live-indicator {state}" role="status">'
        f'<span class="live-indicator__dot" aria-hidden="true"></span>{html.escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_panel_head(title: str, meta: str | None = None) -> None:
    """Render a card heading with an optional small context label on the right."""
    meta_html = f'<span class="panel-head__meta">{html.escape(meta)}</span>' if meta else ""
    st.markdown(
        f'<div class="panel-head"><span class="panel-head__title">{html.escape(title)}</span>'
        f"{meta_html}</div>",
        unsafe_allow_html=True,
    )
