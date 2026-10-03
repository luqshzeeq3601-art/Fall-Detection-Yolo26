"""Overview: high-impact project summary, architecture pipeline, and benchmark metrics."""

from __future__ import annotations

import streamlit as st

from app.components.cards import render_page_header, render_section_header
from app.core.backend import get_backend
from app.core.data_loader import get_benchmark_reports
from app.core.nav import page_button, page_link

_PIPELINE_STEPS = (
    (
        "01",
        ":material/accessibility_new:",
        "Pose Extraction",
        "YOLO26s-Pose",
        "Detects 17 COCO anatomical keypoints (head, shoulders, hips, knees) on every "
        "individual frame in real time with edge GPU acceleration.",
    ),
    (
        "02",
        ":material/timeline:",
        "Temporal Kinematics",
        "Sliding Window Engine",
        "Tracks joint velocities, center-of-mass descent rate, and bounding box aspect "
        "ratio shifts across a rolling temporal history window.",
    ),
    (
        "03",
        ":material/notifications_active:",
        "Post-Fall Verification",
        "Posture Stability Gate",
        "Differentiates true falls from controlled sitting or bending by requiring "
        "sustained floor-level posture (0.45s threshold) following rapid descent.",
    ),
    (
        "04",
        ":material/fact_check:",
        "Human-in-the-Loop",
        "Audit & Fine-Tuning",
        "Stores 3 keyframe snapshots for caregiver confirmation and optional local VLM "
        "explanation. Approved reviews continuously expand the fine-tuning set.",
    ),
)


def _render_kpi_strip() -> None:
    final = get_benchmark_reports().get("final_eval")
    if final is None:
        st.info("Evaluation metrics not found in local artifacts.", icon=":material/info:")
        return

    tb = final["splits"]["test_b"]
    cm, m, tta = tb["confusion_matrix"], tb["metrics"], tb["time_to_alert_seconds"]
    falls = cm["tp"] + cm["fn"]
    alerts = cm["tp"] + cm["false_alerts_total"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="Verified Recall",
            value=f"{m['recall'] * 100:.1f}%",
            delta=f"{cm['tp']} of {falls} falls caught",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Sealed Test-B evaluation across UP-Fall cameras 1 & 2.",
        )
    with c2:
        st.metric(
            label="Verified Precision",
            value=f"{m['precision'] * 100:.1f}%",
            delta=f"{cm['tp']} of {alerts} alerts valid",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Precision on unseen test split without hyperparameter tuning.",
        )
    with c3:
        st.metric(
            label="Median Latency",
            value=f"{tta['median']:.1f} s",
            delta=f"95% within {tta['p95']:.1f} s",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Time from fall onset to alert dispatch.",
        )
    with c4:
        st.metric(
            label="Home False Alarms",
            value="0.00 / hr",
            delta="50 min held-out stream",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Zero false alarms measured on unscripted domestic ADL footage.",
        )


def render_overview_view() -> None:
    """Render the modern minimalist overview landing experience."""
    render_page_header(
        title="ElderCare Vision",
        intro=(
            "A privacy-first, camera-based fall detection engine engineered for senior care. "
            "Processes video locally on edge hardware, identifies rapid descent followed by "
            "sustained ground posture, and alerts caregivers within ~1.1 seconds—distinguishing "
            "genuine emergencies from routine sitting or bending."
        ),
        eyebrow="EDGE AI · TEMPORAL SKELETON REASONING",
        badge_text="v6.3 Sealed",
        badge_color="blue",
    )

    with st.container(horizontal=True, vertical_alignment="center"):
        page_button("live", "Launch Live Demo", ":material/play_arrow:")
        page_link("incidents", "Incident Review Queue", ":material/fact_check:")
        page_link("results", "Sealed Benchmark Results", ":material/analytics:")

    st.divider()

    render_section_header(
        title="Benchmark Scorecard",
        subtitle="Measured once on sealed UP-Fall Test-B (31 sequences, 2 camera angles) after model freeze.",
        icon=":material/analytics:",
    )
    _render_kpi_strip()

    st.divider()

    render_section_header(
        title="Detection Pipeline",
        subtitle="Four-stage temporal architecture designed for high recall and minimal false positives.",
        icon=":material/schema:",
    )
    cols = st.columns(len(_PIPELINE_STEPS))
    for col, (step_num, icon, title, tag, desc) in zip(cols, _PIPELINE_STEPS, strict=True):
        with col.container(border=True, height="stretch"):
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                    <span style="font-size: 0.75rem; font-weight: 700; opacity: 0.5;">STEP {step_num}</span>
                    <span style="font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; background: rgba(140, 149, 159, 0.12); font-weight: 600;">{tag}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(f"**{icon} {title}**")
            st.caption(desc)

    st.divider()

    render_section_header(
        title="Architecture & Operating Boundaries",
        subtitle="Core guarantees and explicit boundary conditions of this research prototype.",
        icon=":material/security:",
    )
    left, right = st.columns(2)
    with left.container(border=True, height="stretch"):
        st.markdown("**:material/lock: Privacy by Design**")
        st.markdown(
            "- **Edge Isolation:** All inference runs on local hardware. Zero continuous video streams are transmitted to any cloud.\n"
            "- **Minimalist Evidence:** Only confirmed alerts persist imagery—specifically 3 keyframes bounding the incident onset.\n"
            "- **On-Device VLM Option:** The optional second-opinion vision model runs locally "
            f"(`{get_backend().vlm_label}`)."
        )
    with right.container(border=True, height="stretch"):
        st.markdown("**:material/gavel: Research Prototype Scope**")
        st.markdown(
            "- **Validation Context:** Calibrated on scripted volunteer fall datasets (UP-Fall & URFD) in controlled laboratory conditions.\n"
            "- **Real-World Baseline:** 0 false alarms on 50 minutes of unscripted domestic video indicates viability, but long-term longitudinal verification is ongoing.\n"
            "- **Safety Positioning:** This system is an engineering demonstration, not a certified life-safety or medical diagnostic appliance."
        )
