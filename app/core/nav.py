"""Page registry so views can link to each other without circular imports."""

from __future__ import annotations

import streamlit as st

PAGES: dict[str, st.Page] = {}


def page_link(key: str, label: str, icon: str | None = None) -> None:
    """Render a link to a registered page (no-op if the page is not registered)."""
    page = PAGES.get(key)
    if page is not None:
        st.page_link(page, label=label, icon=icon)


def page_button(key: str, label: str, icon: str | None = None) -> None:
    """Primary call-to-action button that opens a registered page."""
    page = PAGES.get(key)
    if page is not None and st.button(label, icon=icon, type="primary", key=f"goto_{key}"):
        st.switch_page(page)
