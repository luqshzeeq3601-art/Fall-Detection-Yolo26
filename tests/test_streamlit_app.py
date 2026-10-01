"""Headless unit test for ElderCare Vision Streamlit Application."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_boot() -> None:
    """Test that streamlit_app.py starts cleanly and renders elements."""
    app_path = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.markdown) > 0
