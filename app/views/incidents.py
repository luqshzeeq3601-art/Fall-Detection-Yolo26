"""Incidents & review: real saved falls, AI second opinion, caregiver review, export."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.components.agent_drawer import render_ai_second_opinion
from app.components.cards import render_page_header, render_section_header
from app.core.backend import (
    KEYFRAME_OFFSETS_SEC,
    REVIEW_LABELS,
    DemoBackend,
    IncidentView,
    get_backend,
)
from app.core.nav import page_link

FILTERS = ("Waiting for review", "Flagged by AI", "Reviewed", "All")


def _when(ts: datetime) -> str:
    return ts.astimezone().strftime("%d %b %Y, %H:%M:%S")


def _status_text(inc: IncidentView) -> str:
    review = inc.latest_review
    if review is not None:
        return f"Reviewed: {REVIEW_LABELS.get(review.label, review.label)}"
    return "Flagged by AI, waiting" if inc.flagged_by_ai else "Waiting for review"


def _filter(incidents: list[IncidentView], choice: str) -> list[IncidentView]:
    if choice == "Waiting for review":
        return [i for i in incidents if i.needs_review]
    if choice == "Flagged by AI":
        return [i for i in incidents if i.needs_review and i.flagged_by_ai]
    if choice == "Reviewed":
        return [i for i in incidents if not i.needs_review]
    return incidents


def _keyframes(inc: IncidentView) -> None:
    if not inc.keyframes:
        st.info(
            "No snapshots were persisted for this incident event.",
            icon=":material/image_not_supported:",
        )
        return

    # Stored alert-first; show left to right chronologically
    pairs = list(zip(inc.keyframes, KEYFRAME_OFFSETS_SEC, strict=False))[::-1]
    cols = st.columns(len(pairs))
    for col, (path, offset) in zip(cols, pairs, strict=True):
        caption = "Alert Moment (T=0)" if offset == 0 else f"{offset:g}s Prior to Alert"
        with col.container(border=True):
            st.caption(f"**:material/schedule: {caption}**")
            if path.is_file():
                st.image(str(path), width="stretch")
            else:
                st.warning(f"Snapshot missing: {caption}")


def _review_form(backend: DemoBackend, inc: IncidentView) -> None:
    with st.container(border=True):
        st.markdown(
            """
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
                <span style="font-weight: 600; font-size: 0.95rem;">Caregiver Verification</span>
                <span style="font-size: 0.72rem; opacity: 0.7;">Ground Truth Label</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Your verdict acts as immutable ground truth for downstream model retraining.")

        with st.form(key=f"review_{inc.id}", border=False):
            label = st.radio(
                "Ground truth classification",
                list(REVIEW_LABELS),
                format_func=REVIEW_LABELS.__getitem__,
                horizontal=True,
            )
            reviewer = st.text_input("Reviewer identifier (optional)", max_chars=128)
            notes = st.text_area(
                "Audit notes / observational context",
                placeholder="Observed posture, environment details, or response actions taken...",
                height=90,
            )
            if st.form_submit_button("Submit Verification", type="primary", icon=":material/save:"):
                backend.submit_review(inc.id, label, reviewer.strip(), notes.strip())
                st.toast("Verification submitted successfully", icon=":material/check:")
                st.rerun()

        if inc.reviews:
            st.divider()
            st.markdown("**:material/history: Verification Audit Trail**")
            for r in reversed(inc.reviews):
                who = r.reviewer or "Anonymous Reviewer"
                st.markdown(
                    f"- **{REVIEW_LABELS.get(r.label, r.label)}** · by `{who}` · {_when(r.created_at)}"
                    + (f"<br>&nbsp;&nbsp;_{r.notes}_" if r.notes else ""),
                    unsafe_allow_html=True,
                )


def _export_section(backend: DemoBackend) -> None:
    render_section_header(
        title="Training Corpus Pipeline",
        subtitle="Export verified multi-modal events to expand the frozen model training dataset.",
        icon=":material/dataset:",
    )
    data, count = backend.export_reviewed_jsonl()
    with st.container(border=True):
        st.markdown(
            "Every human-reviewed incident packages 3 temporal keyframes, raw model confidence scores, "
            "advisory VLM opinions, and caregiver labels. Negative feedback (*Not a fall*) provides "
            "crucial hard-negative samples that penalize false alarms in subsequent model training passes."
        )
        st.download_button(
            label=f"Download Verified Corpus ({count} incident{'s' if count != 1 else ''})",
            data=data,
            file_name="reviewed_incidents.jsonl",
            mime="application/jsonl",
            icon=":material/download:",
            type="primary" if count > 0 else "secondary",
            disabled=count == 0,
        )


def render_incidents_view() -> None:
    """Render modern minimalist incident review dashboard."""
    render_page_header(
        title="Incidents & Review",
        intro=(
            "Audit queue for fall incidents flagged by the local inference engine. Inspect "
            "synchronized multi-frame evidence, evaluate advisory vision-language reasoning, and "
            "record human caregiver labels for retraining."
        ),
        eyebrow="HUMAN-IN-THE-LOOP AUDIT · DATASET FLYWHEEL",
        badge_text="Audit Console",
        badge_color="blue",
    )
    backend = get_backend()
    incidents = backend.list_incidents()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Incidents", len(incidents), border=True)
    with c2:
        st.metric("Awaiting Audit", sum(i.needs_review for i in incidents), border=True)
    with c3:
        st.metric(
            "AI Divergence",
            sum(i.needs_review and i.flagged_by_ai for i in incidents),
            border=True,
            help="Incidents where the vision model disagreed or expressed high uncertainty.",
        )
    with c4:
        st.metric("Verified & Cleared", sum(not i.needs_review for i in incidents), border=True)

    if not incidents:
        with st.container(border=True):
            st.markdown("**:material/inbox: Incident Queue Empty**")
            st.caption(
                "No fall incidents have been recorded yet. Launch the Live Demo and trigger a fall sequence."
            )
            page_link("live", "Launch Live Demo", ":material/play_circle:")
        return

    st.divider()

    with st.container(horizontal=True, vertical_alignment="center"):
        choice = st.segmented_control("Queue Filter", FILTERS, default=FILTERS[0]) or FILTERS[-1]
        if st.button("Refresh Queue", icon=":material/refresh:"):
            st.rerun()

    shown = _filter(incidents, choice)
    if not shown:
        st.info(f"No incidents match filter: **{choice}**. Select another filter above.")
        st.divider()
        _export_section(backend)
        return

    selected: IncidentView = st.selectbox(
        "Select Incident to Inspect",
        shown,
        format_func=lambda i: (
            f"{_when(i.confirmed_at)} · Camera: {i.camera_id} · {_status_text(i)}"
        ),
    )

    st.divider()

    left, right = st.columns([0.62, 0.38])
    with left:
        st.markdown(f"#### :material/event: {_when(selected.confirmed_at)}")
        st.caption(
            f"Camera Source: `{selected.camera_id}` · Detector Confidence: `{selected.fall_score * 100:.0f}%` · "
            f"State: `{_status_text(selected)}`"
        )
        st.markdown("**:material/burst_mode: Synchronized Temporal Keyframes**")
        _keyframes(selected)
        render_ai_second_opinion(selected.enrichment, backend.vlm_enabled)

    with right:
        _review_form(backend, selected)

    st.divider()
    _export_section(backend)
