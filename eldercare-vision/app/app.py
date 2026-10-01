"""Streamlit App Entrypoint Forwarder."""

from __future__ import annotations

import runpy
from pathlib import Path

# Forward to root streamlit_app.py
_ROOT_APP = Path(__file__).resolve().parent.parent / "streamlit_app.py"
runpy.run_path(str(_ROOT_APP), run_name="__main__")
