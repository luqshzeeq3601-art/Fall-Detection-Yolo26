"""Overview: what the system does, how well it works, how it works, and its limits."""

from __future__ import annotations

import streamlit as st

from app.components.cards import render_page_header, render_section_header
from app.core.backend import get_backend
from app.core.data_loader import get_benchmark_reports
from app.core.nav import page_button, page_link

_PIPELINE_STEPS = (
    (
        ":material/accessibility_new:",
        "Find the person",
        "YOLO26s-Pose",
        "Marks 17 body points (head, shoulders, hips, knees and more) in every video frame.",
    ),
    (
        ":material/timeline:",
        "Track the movement",
        "Last few seconds of motion",
        "Measures how fast the body drops and how its shape changes over time.",
    ),
    (
        ":material/notifications_active:",
        "Confirm the fall",
        "Must stay on the floor",
        "Alerts only when a fast drop is followed by the person staying low for about "
        "half a second. Sitting down or bending over does not trigger an alert.",
    ),
    (
        ":material/fact_check:",
        "Caregiver checks it",
        "Human review",
        "Each alert saves 3 snapshots so a caregiver can confirm it. Their answers are "
        "used to improve the model.",
    ),
)


def _render_kpi_strip() -> None:
    final = get_benchmark_reports().get("final_eval")
    if final is None:
        st.info(
            "Test results are not available on this machine yet.",
            icon=":material/info:",
        )
        return

    tb = final["splits"]["test_b"]
    cm, m, tta = tb["confusion_matrix"], tb["metrics"], tb["time_to_alert_seconds"]
    falls = cm["tp"] + cm["fn"]
    alerts = cm["tp"] + cm["false_alerts_total"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="Falls caught",
            value=f"{m['recall'] * 100:.1f}%",
            delta=f"{cm['tp']} of {falls} falls",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Share of real falls that raised an alert (recall), on test videos "
            "the model never saw during development.",
        )
    with c2:
        st.metric(
            label="Correct alerts",
            value=f"{m['precision'] * 100:.1f}%",
            delta=f"{cm['tp']} of {alerts} alerts",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Share of alerts that were genuine falls (precision). The rest were false alarms.",
        )
    with c3:
        st.metric(
            label="Typical time to alert",
            value=f"{tta['median']:.1f} s",
            delta=f"95% of alerts within {tta['p95']:.1f} s",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="Time from the start of the fall to the alert (median).",
        )
    with c4:
        st.metric(
            label="False alarms at home",
            value="0 per hour",
            delta="in 50 min of home video",
            delta_color="off",
            delta_arrow="off",
            border=True,
            help="No false alarms on unscripted video of normal daily activity at home.",
        )


def render_overview_view() -> None:
    """Render the overview page."""
    render_page_header(
        title="ElderCare Vision",
        intro=(
            "Watches a camera on this computer and alerts a caregiver when someone falls "
            "and stays on the floor. Normal sitting and bending are ignored, and the video "
            "never leaves this machine."
        ),
        badge_text="Model v6.3",
        badge_color="blue",
        badge_icon=":material/verified:",
    )

    with st.container(horizontal=True, vertical_alignment="center"):
        page_button("live", "Try the Live Demo", ":material/play_arrow:")
        page_link("incidents", "Review incidents", ":material/fact_check:")
        page_link("results", "See test results", ":material/analytics:")

    st.divider()

    render_section_header(
        title="How well it works",
        subtitle="Measured once on test videos the model never saw, filmed from 2 camera angles.",
        icon=":material/analytics:",
    )
    _render_kpi_strip()

    st.divider()

    render_section_header(
        title="How it works",
        subtitle="Four steps run on every video frame, from left to right.",
        icon=":material/schema:",
    )
    cols = st.columns(len(_PIPELINE_STEPS))
    for col, (icon, title, tag, desc) in zip(cols, _PIPELINE_STEPS, strict=True):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{icon} {title}**")
            st.html(f'<span class="chip">{tag}</span>')
            st.caption(desc)

    st.divider()

    render_section_header(
        title="Privacy and limits",
        subtitle="What the system keeps private, and what it has not been proven to do.",
        icon=":material/security:",
    )
    left, right = st.columns(2)
    with left.container(border=True, height="stretch"):
        st.markdown("**:material/lock: What stays private**")
        st.markdown(
            "- All video is processed on this computer. Nothing is streamed to the cloud.\n"
            "- Only confirmed alerts save images: 3 snapshots around the moment of the fall.\n"
            "- The optional AI second opinion also runs locally "
            f"(`{get_backend().vlm_label}`)."
        )
    with right.container(border=True, height="stretch"):
        st.markdown("**:material/gavel: What this demo is not**")
        st.markdown(
            "- Not a certified medical or life-safety device. It is a research prototype.\n"
            "- Tested on volunteers acting out falls in a lab (UP-Fall and URFD datasets), "
            "not on older adults.\n"
            "- No false alarms in 50 minutes of home video is a good sign, but longer "
            "real-world testing is still needed."
        )
