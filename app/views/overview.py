"""Overview: what the project does, how it works, and how well, in plain language."""

from __future__ import annotations

import streamlit as st

from app.components.cards import render_page_header
from app.core.backend import get_backend
from app.core.data_loader import get_benchmark_reports
from app.core.nav import page_button, page_link

_STEPS = (
    (
        ":material/accessibility_new:",
        "1. Find the body",
        "A YOLO26 pose model marks 17 body points (head, shoulders, hips, knees...) "
        "on each person in every video frame.",
    ),
    (
        ":material/timeline:",
        "2. Watch the motion",
        "A small neural network reads the last few seconds of those points and estimates "
        "whether the person is falling, has fallen, or is moving normally.",
    ),
    (
        ":material/notifications_active:",
        "3. Raise the alert",
        "An alert fires only when a fast descent is followed by the person staying low. "
        "That rule is what separates a fall from sitting down or bending over.",
    ),
    (
        ":material/fact_check:",
        "4. Double-check and learn",
        "Each alert is saved with snapshots. An optional AI model gives a second opinion, "
        "a caregiver confirms or rejects it, and confirmed labels become new training data.",
    ),
)


def _results_section() -> None:
    final = get_benchmark_reports().get("final_eval")
    if final is None:
        st.info("Evaluation results are not available in this copy of the project.")
        return
    tb = final["splits"]["test_b"]
    cm, m, tta = tb["confusion_matrix"], tb["metrics"], tb["time_to_alert_seconds"]
    falls = cm["tp"] + cm["fn"]
    alerts = cm["tp"] + cm["false_alerts_total"]

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Falls caught",
        f"{cm['tp']} of {falls}",
        f"{m['recall'] * 100:.1f}% recall",
        delta_color="off",
        delta_arrow="off",
        border=True,
    )
    c2.metric(
        "Alerts that were real falls",
        f"{cm['tp']} of {alerts}",
        f"{m['precision'] * 100:.1f}% precision",
        delta_color="off",
        delta_arrow="off",
        border=True,
    )
    c3.metric(
        "Typical time to alert",
        f"{tta['median']:.1f} s",
        f"95% of alerts within {tta['p95']:.1f} s",
        delta_color="off",
        delta_arrow="off",
        border=True,
    )
    st.caption(
        f"Measured once, after the model was frozen, on {tb['total_sequences']} test videos "
        "the model never saw during development (UP-Fall dataset, 2 cameras)."
    )


def render_overview_view() -> None:
    """Landing page for first-time visitors."""
    render_page_header(
        "ElderCare Vision",
        "A camera-based fall detector for elder care. It watches ordinary video, notices when "
        "someone falls, and alerts a caregiver within about a second, while ignoring everyday "
        "movements like sitting down or picking something up.",
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        page_button("live", "Try the live demo", ":material/play_arrow:")
        page_link("incidents", "Review detected falls", ":material/fact_check:")
        page_link("results", "See the full results", ":material/analytics:")

    st.subheader("How it works")
    cols = st.columns(len(_STEPS))
    for col, (icon, title, body) in zip(cols, _STEPS, strict=True):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{icon} {title}**")
            st.markdown(body)

    st.subheader("How well it works")
    _results_section()

    left, right = st.columns(2)
    with left.container(border=True, height="stretch"):
        st.markdown("**:material/lock: Privacy**")
        st.markdown(
            "- Video is processed on this computer. Nothing is uploaded.\n"
            "- Only alerts store images: three snapshots around the moment of the fall.\n"
            "- The optional AI second opinion is meant to run on a local model. "
            f"In this demo it is: **{get_backend().vlm_label}**."
        )
    with right.container(border=True, height="stretch"):
        st.markdown("**:material/info: Limits to keep in mind**")
        st.markdown(
            "- Tested on staged falls by volunteers in a lab, not on real residents.\n"
            "- The false-alarm rate in real homes is not proven yet: 0 false alarms in "
            "50 minutes of home video is encouraging but far too little to be sure.\n"
            "- It is a research prototype, not a certified medical device."
        )
