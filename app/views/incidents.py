"""Incidents & review: real saved falls, AI second opinion, caregiver review, export."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from app.components.agent_drawer import render_ai_second_opinion
from app.components.cards import render_page_header
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
        st.info("No snapshots were saved for this incident.")
        return
    # Stored alert-first; show left to right in time order.
    pairs = list(zip(inc.keyframes, KEYFRAME_OFFSETS_SEC, strict=False))[::-1]
    cols = st.columns(len(pairs))
    for col, (path, offset) in zip(cols, pairs, strict=True):
        caption = "At the alert" if offset == 0 else f"{offset:g} s before the alert"
        if path.is_file():
            col.image(str(path), caption=caption, width="stretch")
        else:
            col.warning(f"Snapshot missing: {caption}")


def _review_form(backend: DemoBackend, inc: IncidentView) -> None:
    with st.container(border=True):
        st.markdown("#### :material/person_check: Your review")
        st.caption("Your answer is the final label. It is what the model learns from next.")
        with st.form(key=f"review_{inc.id}", border=False):
            label = st.radio(
                "Was this a real fall?",
                list(REVIEW_LABELS),
                format_func=REVIEW_LABELS.__getitem__,
                horizontal=True,
            )
            reviewer = st.text_input("Your name (optional)", max_chars=128)
            notes = st.text_area(
                "Notes (optional)",
                placeholder="What you saw, what action was taken",
                height=90,
            )
            if st.form_submit_button("Save review", type="primary", icon=":material/save:"):
                backend.submit_review(inc.id, label, reviewer.strip(), notes.strip())
                st.toast("Review saved", icon=":material/check:")
                st.rerun()

        if inc.reviews:
            st.markdown("**History**")
            for r in reversed(inc.reviews):
                who = r.reviewer or "Anonymous"
                st.markdown(
                    f"- {REVIEW_LABELS.get(r.label, r.label)}, by {who}, {_when(r.created_at)}"
                    + (f": _{r.notes}_" if r.notes else "")
                )


def _export_section(backend: DemoBackend) -> None:
    st.subheader("Training data")
    data, count = backend.export_reviewed_jsonl()
    st.markdown(
        "Each reviewed incident becomes one training example: the snapshots, the detector's "
        "score, the AI's opinion and your label. Incidents marked *Not a fall* matter most, "
        "because they teach the detector which movements to ignore."
    )
    st.download_button(
        f"Download {count} reviewed incident(s) (JSONL)",
        data=data,
        file_name="reviewed_incidents.jsonl",
        mime="application/jsonl",
        icon=":material/download:",
        disabled=count == 0,
    )
    st.caption(
        "Same export from the command line: "
        "`python scripts/export_reviewed_dataset.py --database-url "
        "sqlite:///demo_data/eldercare_demo.db --out reviewed.jsonl`. "
        "Snapshot paths are relative to `demo_data/evidence/`."
    )


def render_incidents_view() -> None:
    """Incident review page."""
    render_page_header(
        "Incidents & review",
        "Every fall the detector raises is saved here with snapshots from just before and at "
        "the alert. An AI model can add a second opinion; a person makes the final call.",
    )
    backend = get_backend()
    incidents = backend.list_incidents()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incidents", len(incidents), border=True)
    c2.metric("Waiting for review", sum(i.needs_review for i in incidents), border=True)
    c3.metric(
        "Flagged by AI",
        sum(i.needs_review and i.flagged_by_ai for i in incidents),
        border=True,
        help="The AI was unsure or did not see a fall. These deserve a look first.",
    )
    c4.metric("Reviewed", sum(not i.needs_review for i in incidents), border=True)

    if not incidents:
        with st.container(border=True):
            st.markdown("**No incidents yet.**")
            st.markdown("Run a fall example in the live demo. The detected fall will appear here.")
            page_link("live", "Open the live demo", ":material/play_circle:")
        return

    with st.container(horizontal=True, vertical_alignment="bottom"):
        choice = st.segmented_control("Show", FILTERS, default=FILTERS[0]) or FILTERS[-1]
        if st.button("Refresh", icon=":material/refresh:"):
            st.rerun()
    shown = _filter(incidents, choice)
    if not shown:
        st.info(f"Nothing in **{choice}**. Pick another filter above.")
        _export_section(backend)
        return

    selected: IncidentView = st.selectbox(
        "Incident",
        shown,
        format_func=lambda i: f"{_when(i.confirmed_at)} · {i.camera_id} · {_status_text(i)}",
    )

    st.divider()
    left, right = st.columns([0.62, 0.38])
    with left:
        st.markdown(f"#### {_when(selected.confirmed_at)} · {selected.camera_id}")
        st.caption(
            f"Detector confidence {selected.fall_score * 100:.0f}% · {_status_text(selected)}"
        )
        _keyframes(selected)
        render_ai_second_opinion(selected.enrichment, backend.vlm_enabled)
    with right:
        _review_form(backend, selected)

    st.divider()
    _export_section(backend)
