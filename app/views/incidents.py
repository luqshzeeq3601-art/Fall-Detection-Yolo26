"""Incidents & review: real saved falls, AI second opinion, caregiver review, export."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.components.agent_drawer import render_ai_second_opinion
from app.components.cards import render_page_header, render_panel_head, render_section_header
from app.core.backend import (
    KEYFRAME_OFFSETS_SEC,
    REVIEW_LABELS,
    DemoBackend,
    IncidentView,
    get_backend,
)
from app.core.nav import page_link

FILTERS = ("Waiting for review", "AI disagrees", "Reviewed", "All")


def _when(ts: datetime) -> str:
    return ts.astimezone().strftime("%d %b %Y, %H:%M:%S")


def _status_text(inc: IncidentView) -> str:
    review = inc.latest_review
    if review is not None:
        return f"Reviewed: {REVIEW_LABELS.get(review.label, review.label)}"
    return "AI disagrees, waiting for review" if inc.flagged_by_ai else "Waiting for review"


def _filter(incidents: list[IncidentView], choice: str) -> list[IncidentView]:
    if choice == "Waiting for review":
        return [i for i in incidents if i.needs_review]
    if choice == "AI disagrees":
        return [i for i in incidents if i.needs_review and i.flagged_by_ai]
    if choice == "Reviewed":
        return [i for i in incidents if not i.needs_review]
    return incidents


def _keyframes(inc: IncidentView) -> None:
    if not inc.keyframes:
        st.info(
            "No snapshots were saved for this incident.",
            icon=":material/image_not_supported:",
        )
        return

    # Stored alert-first; show left to right chronologically
    pairs = list(zip(inc.keyframes, KEYFRAME_OFFSETS_SEC, strict=False))[::-1]
    cols = st.columns(len(pairs))
    for col, (path, offset) in zip(cols, pairs, strict=True):
        caption = "At the alert" if offset == 0 else f"{offset:g} s before the alert"
        with col.container(border=True):
            st.caption(f"**:material/schedule: {caption}**")
            if path.is_file():
                st.image(str(path), width="stretch")
            else:
                st.warning(f"Snapshot file missing ({caption.lower()})")


def _review_form(backend: DemoBackend, inc: IncidentView) -> None:
    with st.container(border=True):
        render_panel_head("Your review", "Was this a real fall?")
        st.caption("Your answer is saved as the correct label and used to improve the model.")

        with st.form(key=f"review_{inc.id}", border=False):
            label = st.radio(
                "What happened?",
                list(REVIEW_LABELS),
                format_func=REVIEW_LABELS.__getitem__,
                horizontal=True,
            )
            reviewer = st.text_input("Your name or ID (optional)", max_chars=128)
            notes = st.text_area(
                "Notes (optional)",
                placeholder="For example: slipped near the bed and stayed down, helped up after 2 minutes.",
                height=90,
            )
            if st.form_submit_button("Save review", type="primary", icon=":material/save:"):
                backend.submit_review(inc.id, label, reviewer.strip(), notes.strip())
                st.toast("Review saved", icon=":material/check:")
                st.rerun()

        if inc.reviews:
            st.divider()
            st.markdown("**:material/history: Review history**")
            for r in reversed(inc.reviews):
                who = r.reviewer or "Anonymous"
                st.markdown(
                    f"- **{REVIEW_LABELS.get(r.label, r.label)}** · by `{who}` · {_when(r.created_at)}"
                    + (f"<br>&nbsp;&nbsp;_{r.notes}_" if r.notes else ""),
                    unsafe_allow_html=True,
                )


def _export_section(backend: DemoBackend) -> None:
    render_section_header(
        title="Export reviewed incidents",
        subtitle="Download your reviews to add them to the model's training data.",
        icon=":material/dataset:",
    )
    data, count = backend.export_reviewed_jsonl()
    with st.container(border=True):
        st.markdown(
            "Each reviewed incident includes its 3 snapshots, the detector's score, the AI "
            "second opinion and your answer. Incidents marked **Not a fall** are especially "
            "useful: they teach the model to avoid that false alarm next time."
        )
        st.download_button(
            label=f"Download {count} reviewed incident{'s' if count != 1 else ''} (JSONL)",
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
            "Every fall the detector confirms is listed here. Pick an incident, look at the "
            "3 snapshots, then tell us whether it was a real fall."
        ),
        badge_text="Human review",
        badge_color="blue",
        badge_icon=":material/person_check:",
    )
    backend = get_backend()
    incidents = backend.list_incidents()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("All incidents", len(incidents), border=True)
    with c2:
        st.metric("Waiting for review", sum(i.needs_review for i in incidents), border=True)
    with c3:
        st.metric(
            "AI disagrees",
            sum(i.needs_review and i.flagged_by_ai for i in incidents),
            border=True,
            help="The AI second opinion disagreed with the detector or was unsure. "
            "Review these first.",
        )
    with c4:
        st.metric("Reviewed", sum(not i.needs_review for i in incidents), border=True)

    if not incidents:
        with st.container(border=True):
            st.markdown("**:material/inbox: No incidents yet**")
            st.caption(
                "Incidents appear here after the Live Demo detects a fall. "
                "Try one of the **Fall example** clips."
            )
            page_link("live", "Open Live Demo", ":material/play_circle:")
        return

    st.divider()

    with st.container(horizontal=True, vertical_alignment="bottom"):
        choice = st.segmented_control("Show", FILTERS, default=FILTERS[0]) or FILTERS[-1]
        if st.button("Refresh", icon=":material/refresh:"):
            st.rerun()

    shown = _filter(incidents, choice)
    if not shown:
        st.info(
            f"Nothing in **{choice}** right now. Choose **All** to see every incident.",
            icon=":material/filter_alt_off:",
        )
        st.divider()
        _export_section(backend)
        return

    selected: IncidentView = st.selectbox(
        "Incident",
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
            f"Camera: `{selected.camera_id}`  \n"
            f"Detector confidence: **{selected.fall_score * 100:.0f}%**  \n"
            f"Status: **{_status_text(selected)}**"
        )
        st.markdown("**:material/burst_mode: Snapshots around the fall**")
        _keyframes(selected)
        render_ai_second_opinion(selected.enrichment, backend.vlm_enabled)

    with right:
        _review_form(backend, selected)

    st.divider()
    _export_section(backend)
