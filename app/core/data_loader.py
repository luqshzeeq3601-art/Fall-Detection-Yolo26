"""Data loader for ElderCare Vision Streamlit App.

Loads:
- Sample test video clips from datasets/raw/urfd
- Benchmark reports and model evaluation JSONs from models/
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class VideoClip:
    """Metadata for a demo video clip."""

    name: str
    path: Path
    category: str  # "fall" or "adl"
    description: str


@st.cache_data
def get_sample_videos() -> list[VideoClip]:
    """Discover available sample videos in the repository."""
    urfd_dir = PROJECT_ROOT / "datasets" / "raw" / "urfd"
    clips: list[VideoClip] = []

    if urfd_dir.is_dir():
        # Falls
        fall_files = sorted(urfd_dir.glob("fall-*.mp4"))
        for f in fall_files[:5]:  # First 5 falls
            clips.append(
                VideoClip(
                    name=f"Fall example {f.stem.split('-')[1]}",
                    path=f,
                    category="fall",
                    description="Staged fall from the public URFD dataset (UR Fall Detection)",
                )
            )

        # ADLs (Activities of Daily Living)
        adl_files = sorted(urfd_dir.glob("adl-*.mp4"))
        for f in adl_files[:5]:  # First 5 ADLs
            clips.append(
                VideoClip(
                    name=f"Everyday activity {f.stem.split('-')[1]}",
                    path=f,
                    category="adl",
                    description="Everyday activity with no fall (sitting, bending, lying down) from URFD",
                )
            )

    return clips


PHASE_MODEL_DIRS = (
    ("Phase 0 (audited baseline)", "v6_1_phase0"),
    ("Phase 2 (multi-person + v2)", "v6_2_phase2_mp"),
    ("Phase 3 (handover fix)", "v6_3_phase3"),
    ("Phase 3 + descent (frozen)", "v6_3_phase3b"),
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


@st.cache_data
def get_benchmark_reports() -> dict[str, Any]:
    """Final sealed evaluation, freeze manifest and per-phase training reports."""
    models_dir = PROJECT_ROOT / "models"
    reports: dict[str, Any] = {
        "final_eval": _read_json(
            PROJECT_ROOT / "docs" / "reports" / "V6_3_FINAL_TESTB_EVALUATION.json"
        ),
        "freeze": _read_json(models_dir / "v6_3_phase3b" / "freeze_manifest.json"),
        "phases": [],
    }
    for name, folder in PHASE_MODEL_DIRS:
        rep = _read_json(models_dir / folder / "v6_training_report.json")
        if rep is not None and "event_level_dev_metrics" in rep:
            reports["phases"].append((name, rep))
    return reports
