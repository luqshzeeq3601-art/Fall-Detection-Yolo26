"""ElderCare Vision Streamlit Application Package."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root and src/ directory are on sys.path
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
