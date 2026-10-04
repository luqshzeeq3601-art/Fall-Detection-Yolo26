"""Unit tests for ElderCare Vision Evaluation Dashboard Streamlit Application."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


def test_evaluation_dashboard_boot() -> None:
    """Verify that apps/evaluation_dashboard.py starts cleanly and renders all elements without error."""
    app_path = ROOT / "apps" / "evaluation_dashboard.py"
    at = AppTest.from_file(str(app_path), default_timeout=30)
    at.run()

    assert not at.exception
    # Check that main headers and metric elements are rendered
    assert len(at.metric) >= 5
    # Verify Recall and Precision metric labels exist
    labels = [m.label for m in at.metric]
    assert any("Recall" in lbl for lbl in labels)
    assert any("Precision" in lbl for lbl in labels)
    assert any("F1" in lbl for lbl in labels)
    assert any("FPS" in lbl for lbl in labels)
