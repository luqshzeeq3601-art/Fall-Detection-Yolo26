"""Shared page-level building blocks for ElderCare Vision."""

from __future__ import annotations

import html

import streamlit as st


def render_page_header(title: str, intro: str) -> None:
    """Page title plus one plain-language paragraph saying what the page is for."""
    st.title(title)
    st.markdown(f'<p class="page-intro">{html.escape(intro)}</p>', unsafe_allow_html=True)


# Detection state -> (label shown to people, badge color, icon). Text and icon carry
# the meaning, so the state never depends on color alone.
STATUS_STYLES: dict[str, tuple[str, str, str]] = {
    "IDLE": ("Ready", "gray", ":material/pause_circle:"),
    "NORMAL": ("Watching: no fall", "green", ":material/check_circle:"),
    "NO_PERSON": ("Watching: no person in view", "gray", ":material/visibility:"),
    "FALLING": ("Possible fall: confirming", "orange", ":material/warning:"),
    "FALL_DETECTED": ("Fall detected: alert raised", "red", ":material/emergency:"),
}


def render_status_badge(state: str) -> None:
    """Large status line for the live detection state."""
    label, color, icon = STATUS_STYLES.get(state, STATUS_STYLES["IDLE"])
    st.badge(label, color=color, icon=icon)
