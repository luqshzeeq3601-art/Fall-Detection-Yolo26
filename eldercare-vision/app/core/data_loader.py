"""Data loader for ElderCare Vision Streamlit App.

Loads:
- Sample test video clips from datasets/raw/urfd
- Benchmark reports and model evaluation JSONs from models/
- Incident records and mock evidence snapshots for demonstration
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
                    name=f"URFD {f.stem.upper()}",
                    path=f,
                    category="fall",
                    description="Real elder-care fall sequence recorded by CCTV Cam0",
                )
            )

        # ADLs (Activities of Daily Living)
        adl_files = sorted(urfd_dir.glob("adl-*.mp4"))
        for f in adl_files[:5]:  # First 5 ADLs
            clips.append(
                VideoClip(
                    name=f"URFD {f.stem.upper()}",
                    path=f,
                    category="adl",
                    description="Normal daily activity (walking, sitting, bending) without falls",
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


@dataclass
class IncidentItem:
    """Incident record for incident review station."""

    id: str
    timestamp: str
    camera_id: str
    camera_name: str
    confidence: float
    status: str  # "PENDING_REVIEW", "CONFIRMED_FALL", "FALSE_POSITIVE"
    duration_sec: float
    pre_onset_time: str
    impact_time: str
    post_fall_time: str
    vlm_summary: str
    kinetic_score: float
    floor_distance_score: float
    adl_suppression_score: float
    reviewed_by: str | None = None
    review_notes: str | None = None


def get_default_incidents() -> list[IncidentItem]:
    """Provide realistic demo incidents."""
    return [
        IncidentItem(
            id="INC-2026-0929-01",
            timestamp="2026-09-29 14:22:18",
            camera_id="CAM-01",
            camera_name="Living Area East (Cam 01)",
            confidence=0.96,
            status="PENDING_REVIEW",
            duration_sec=3.8,
            pre_onset_time="14:22:15 (-3.0s)",
            impact_time="14:22:18 (0.0s)",
            post_fall_time="14:22:21 (+3.0s)",
            vlm_summary=(
                "Patient lost balance while walking away from armchair. Rapid downward vertical velocity "
                "detected (dy/dt = -1.82 m/s). Subject landed on linoleum floor in lateral decubitus posture. "
                "No self-recovery movement observed for 3.8 seconds. Emergency alert triggered."
            ),
            kinetic_score=0.94,
            floor_distance_score=0.97,
            adl_suppression_score=0.12,
        ),
        IncidentItem(
            id="INC-2026-0929-02",
            timestamp="2026-09-29 11:05:40",
            camera_id="CAM-02",
            camera_name="Corridor Ward B (Cam 02)",
            confidence=0.91,
            status="CONFIRMED_FALL",
            duration_sec=4.5,
            pre_onset_time="11:05:37 (-3.0s)",
            impact_time="11:05:40 (0.0s)",
            post_fall_time="11:05:44 (+4.0s)",
            vlm_summary=(
                "Slip and fall incident near nursing station doorway. Bounding box aspect ratio flipped "
                "from 0.38 (standing) to 2.15 (recumbent). Staff response dispatched within 45 seconds."
            ),
            kinetic_score=0.89,
            floor_distance_score=0.93,
            adl_suppression_score=0.08,
            reviewed_by="Nurse Coordinator Sarah M.",
            review_notes="Assistance provided immediately. Minor knee contusion, patient stabilized.",
        ),
        IncidentItem(
            id="INC-2026-0928-03",
            timestamp="2026-09-28 18:41:12",
            camera_id="CAM-03",
            camera_name="Dining Hall West (Cam 03)",
            confidence=0.48,
            status="FALSE_POSITIVE",
            duration_sec=1.2,
            pre_onset_time="18:41:09 (-3.0s)",
            impact_time="18:41:12 (0.0s)",
            post_fall_time="18:41:15 (+3.0s)",
            vlm_summary=(
                "Rapid sitting motion into low-slung sofa. Kinetic threshold momentarily exceeded but "
                "torso remained supported above floor plane. ADL false alarm suppression rule active."
            ),
            kinetic_score=0.52,
            floor_distance_score=0.31,
            adl_suppression_score=0.88,
            reviewed_by="Automated ADL Filter / Admin",
            review_notes="Classified as rapid sitting; safely suppressed.",
        ),
    ]
