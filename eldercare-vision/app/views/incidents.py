"""Incident Management & Evidence Review Station for ElderCare Vision."""

from __future__ import annotations

import json

import cv2
import numpy as np
import streamlit as st

from app.components.agent_drawer import render_vlm_agent_drawer
from app.components.cards import render_demo_tour_guide, render_header
from app.core.data_loader import IncidentItem


def generate_synthetic_evidence_frame(
    stage: str,
    label: str,
    accent_color: tuple[int, int, int],
) -> np.ndarray:
    """Generate high-contrast annotated evidence frame for incident review."""
    img = np.full((320, 480, 3), 245, dtype=np.uint8)  # Light clinical gray background

    # Floor line
    cv2.line(img, (0, 260), (480, 260), (200, 200, 200), 2)
    cv2.putText(img, "FLOOR LEVEL", (10, 255), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1)

    # Simplified Stick Skeleton depending on stage
    if stage == "PRE":
        # Upright person
        cv2.circle(img, (240, 100), 18, (37, 99, 235), -1)  # Head
        cv2.line(img, (240, 118), (240, 190), accent_color, 3)  # Torso
        cv2.line(img, (240, 130), (210, 160), accent_color, 2)  # Left arm
        cv2.line(img, (240, 130), (270, 160), accent_color, 2)  # Right arm
        cv2.line(img, (240, 190), (220, 255), accent_color, 3)  # Left leg
        cv2.line(img, (240, 190), (260, 255), accent_color, 3)  # Right leg
        cv2.rectangle(img, (190, 80), (290, 260), accent_color, 2)
    elif stage == "IMPACT":
        # Diagonal falling posture
        cv2.circle(img, (180, 180), 18, (37, 99, 235), -1)  # Head
        cv2.line(img, (180, 198), (250, 230), accent_color, 3)  # Torso
        cv2.line(img, (200, 205), (170, 240), accent_color, 2)  # Arm
        cv2.line(img, (250, 230), (320, 260), accent_color, 3)  # Legs
        cv2.rectangle(img, (160, 160), (330, 270), accent_color, 2)
    else:  # POST
        # Horizontal recumbent on floor
        cv2.circle(img, (140, 245), 18, (37, 99, 235), -1)  # Head
        cv2.line(img, (158, 245), (270, 245), accent_color, 3)  # Torso
        cv2.line(img, (190, 245), (180, 220), accent_color, 2)  # Arm
        cv2.line(img, (270, 245), (360, 250), accent_color, 3)  # Legs
        cv2.rectangle(img, (120, 220), (370, 270), accent_color, 2)

    # Label Banner
    cv2.rectangle(img, (10, 10), (280, 40), (255, 255, 255), -1)
    cv2.rectangle(img, (10, 10), (280, 40), (200, 210, 220), 1)
    cv2.putText(img, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, accent_color, 1, cv2.LINE_AA)

    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def render_incidents_view() -> None:
    """Render the incident review station with evidence snapshots and VLM agent."""
    render_header(
        title="Incident Management & Evidence Station",
        subtitle="Forensic Evidence Review, Multimodal Scene Reasoning & Clinical Verification",
        status_text="AUDIT LOG ACTIVE",
        status_variant="agent",
    )

    render_demo_tour_guide(
        page_title="Incident Review",
        steps=[
            "View real-time and historical fall events logged by the edge inference engine.",
            "Inspect the **3-Frame Temporal Evidence Strip** (Pre-fall onset, Impact, Post-fall lying).",
            "Read the **Ultralytics VLM Agent Scene Summary** providing human-interpretable clinical context.",
            "Perform live caregiver triage: Confirm falls or mark false alarms with audit logging.",
        ],
    )

    incidents: list[IncidentItem] = st.session_state.get("incidents", [])

    # KPI Summary Row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Total Logged Events", len(incidents), border=True)
    with kpi2:
        pending_count = sum(1 for i in incidents if i.status == "PENDING_REVIEW")
        st.metric("Pending Review", pending_count, "Requires Triage", delta_color="inverse", border=True)
    with kpi3:
        confirmed_count = sum(1 for i in incidents if i.status == "CONFIRMED_FALL")
        st.metric("Confirmed Falls", confirmed_count, "Emergency Escalated", border=True)
    with kpi4:
        suppressed_count = sum(1 for i in incidents if i.status == "FALSE_POSITIVE")
        st.metric("Suppressed ADL", suppressed_count, "Filtered by Engine", border=True)

    # Filter selector
    filter_choice = st.pills(
        "Filter Incidents by Status",
        options=["All", "Pending Review", "Confirmed Fall", "False Positive"],
        default="All",
        label_visibility="collapsed",
    )

    filtered_incidents = incidents
    if filter_choice == "Pending Review":
        filtered_incidents = [i for i in incidents if i.status == "PENDING_REVIEW"]
    elif filter_choice == "Confirmed Fall":
        filtered_incidents = [i for i in incidents if i.status == "CONFIRMED_FALL"]
    elif filter_choice == "False Positive":
        filtered_incidents = [i for i in incidents if i.status == "FALSE_POSITIVE"]

    if not filtered_incidents:
        st.info("No incidents match the selected filter.")
        return

    # Incident Selection
    options_dict = {f"{i.id} — {i.camera_name} ({i.timestamp})": i for i in filtered_incidents}
    selected_label = st.selectbox(
        "Select Incident to Inspect",
        options=list(options_dict.keys()),
        index=0,
    )
    selected_inc: IncidentItem = options_dict[selected_label]

    st.divider()

    # Incident Detail View
    det_col1, det_col2 = st.columns([0.65, 0.35])

    with det_col1:
        st.markdown(f"### {selected_inc.id} — Temporal Evidence Sequence")
        st.caption(f"Camera: **{selected_inc.camera_name}** | Event Onset: **{selected_inc.timestamp}**")

        # 3-Frame Snapshot Viewer
        snap_col1, snap_col2, snap_col3 = st.columns(3)
        with snap_col1:
            frame_pre = generate_synthetic_evidence_frame("PRE", "1. Pre-Onset (-3.0s)", (16, 185, 129))
            st.image(frame_pre, caption=f"Pre-Fall: {selected_inc.pre_onset_time}", width="stretch")
        with snap_col2:
            frame_impact = generate_synthetic_evidence_frame("IMPACT", "2. Impact (0.0s)", (245, 158, 11))
            st.image(frame_impact, caption=f"Impact Frame: {selected_inc.impact_time}", width="stretch")
        with snap_col3:
            frame_post = generate_synthetic_evidence_frame("POST", "3. Lying (+3.0s)", (239, 68, 68))
            st.image(frame_post, caption=f"Post-Fall Lying: {selected_inc.post_fall_time}", width="stretch")

        # Ultralytics VLM Agent Drawer
        render_vlm_agent_drawer(
            vlm_summary=selected_inc.vlm_summary,
            kinetic_score=selected_inc.kinetic_score,
            floor_score=selected_inc.floor_distance_score,
            adl_score=selected_inc.adl_suppression_score,
            confidence=selected_inc.confidence,
        )

    with det_col2:
        with st.container(border=True):
            st.markdown("#### Clinical Review & Dispatch")

            # Status Badge
            if selected_inc.status == "CONFIRMED_FALL":
                st.markdown("Status: <span class='status-badge badge-alarm'>🚨 CONFIRMED FALL</span>", unsafe_allow_html=True)
            elif selected_inc.status == "FALSE_POSITIVE":
                st.markdown("Status: <span class='status-badge badge-safe'>● FALSE ALARM</span>", unsafe_allow_html=True)
            else:
                st.markdown("Status: <span class='status-badge badge-warning'>⚠️ PENDING REVIEW</span>", unsafe_allow_html=True)

            st.write(f"**Confidence:** `{selected_inc.confidence * 100:.1f}%`")
            st.write(f"**Duration Recumbent:** `{selected_inc.duration_sec:.1f}s`")

            st.divider()

            # Caretaker Action Form
            with st.form(key=f"review_form_{selected_inc.id}"):
                new_status = st.selectbox(
                    "Triage Decision",
                    options=["PENDING_REVIEW", "CONFIRMED_FALL", "FALSE_POSITIVE"],
                    index=["PENDING_REVIEW", "CONFIRMED_FALL", "FALSE_POSITIVE"].index(selected_inc.status),
                )
                reviewer = st.text_input(
                    "Reviewer Name",
                    value=selected_inc.reviewed_by or "Nurse Coordinator On-Duty",
                )
                notes = st.text_area(
                    "Clinical Audit Notes",
                    value=selected_inc.review_notes or "Immediate assistance dispatched. Patient assisted to sitting position.",
                    height=100,
                )
                submitted = st.form_submit_button("Submit Triage Decision", type="primary", width="stretch")

                if submitted:
                    selected_inc.status = new_status
                    selected_inc.reviewed_by = reviewer
                    selected_inc.review_notes = notes
                    st.toast(f"Incident {selected_inc.id} updated to {new_status}!", icon="✅")
                    st.rerun()

            # Export Audit Package
            incident_json = json.dumps(
                {
                    "incident_id": selected_inc.id,
                    "timestamp": selected_inc.timestamp,
                    "camera_id": selected_inc.camera_id,
                    "confidence": selected_inc.confidence,
                    "status": selected_inc.status,
                    "vlm_summary": selected_inc.vlm_summary,
                    "reviewed_by": selected_inc.reviewed_by,
                    "review_notes": selected_inc.review_notes,
                },
                indent=2,
            )
            st.download_button(
                "📥 Export Incident Audit JSON",
                data=incident_json,
                file_name=f"{selected_inc.id}_audit.json",
                mime="application/json",
                width="stretch",
            )
