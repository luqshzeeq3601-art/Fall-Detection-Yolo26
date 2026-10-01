"""Skip markers for tests that need git-ignored local artifacts.

Raw datasets, pose weights and TensorRT engines are not committed (see .gitignore),
so tests that verify them can only run on a machine that has them. On a fresh clone
or CI they skip with a clear reason instead of failing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def requires_local(*rel_paths: str) -> pytest.MarkDecorator:
    """Skip the test unless every repo-relative path exists locally."""
    missing = [p for p in rel_paths if not (REPO_ROOT / p).exists()]
    return pytest.mark.skipif(
        bool(missing),
        reason=f"local-only artifact not present: {', '.join(missing)}",
    )
