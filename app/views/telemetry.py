"""System status: real hardware and model pipeline telemetry from the local host."""

from __future__ import annotations

import psutil
import streamlit as st
import torch

from app.components.cards import render_page_header, render_section_header
from app.core.backend import get_backend
from app.core.inference_runner import load_frozen_fall_model, load_pose_model


def render_telemetry_view() -> None:
    """Hardware, model weights, and pipeline status for this demo instance."""
    render_page_header(
        title="System Telemetry",
        intro=(
            "Checks that this computer and the detector are ready to run. "
            "Green means working; grey means turned off or missing."
        ),
        badge_text="Host online",
        badge_color="green",
        badge_icon=":material/check_circle:",
    )

    render_section_header(
        title="This computer",
        subtitle="Current usage, updated each time you open this page.",
        icon=":material/memory:",
    )

    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    backend = get_backend()
    disk = psutil.disk_usage(str(backend.data_dir))
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="Processor in use",
            value=f"{cpu:.0f}%",
            delta="Normal" if cpu < 80 else "Busy, video may lag",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c2:
        st.metric(
            label="Memory in use",
            value=f"{ram.percent:.0f}%",
            delta=f"{ram.used / 1024**3:.1f} of {ram.total / 1024**3:.1f} GB",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c3:
        st.metric(
            label="Runs on",
            value="GPU" if gpu else "CPU",
            delta=gpu[:26] if gpu else "No NVIDIA GPU found",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c4:
        st.metric(
            label="Free disk space",
            value=f"{disk.free / 1024**3:.0f} GB",
            delta="Where snapshots are saved",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )

    st.divider()

    render_section_header(
        title="Detector parts",
        subtitle="Each part the demo needs, whether it is ready, and the file it uses.",
        icon=":material/developer_board:",
    )

    subsystems = [
        (
            "Body point finder (YOLO26s-Pose)",
            load_pose_model() is not None,
            "Finds 17 body points in each frame",
            "models/yolo26s-pose.pt",
        ),
        (
            "Fall classifier (v6.3)",
            load_frozen_fall_model() is not None,
            "Decides whether a fall happened",
            "models/v6_3_phase3b/",
        ),
        (
            "Incident database",
            True,
            "Stores incidents and reviews",
            f"{backend.data_dir.name}/eldercare_demo.db",
        ),
        (
            "AI second opinion (optional)",
            backend.vlm_enabled,
            "Describes each alert in words",
            backend.vlm_label,
        ),
    ]

    with st.container(border=True):
        for name, active, purpose, artifact in subsystems:
            col_state, col_info, col_path = st.columns(
                [0.3, 0.35, 0.35], vertical_alignment="center"
            )
            with col_state:
                st.markdown(f"**{name}**")
                st.badge(
                    "Ready" if active else "Off or missing",
                    color="green" if active else "gray",
                    icon=":material/check_circle:"
                    if active
                    else ":material/radio_button_unchecked:",
                )
            with col_info:
                st.caption(purpose)
            with col_path:
                st.code(artifact, language="bash")

    st.divider()

    with st.container(border=True):
        st.markdown("**:material/lan: How alerts are sent**")
        st.caption(
            "This demo runs on its own and keeps everything on this computer. In a full "
            "installation, alerts are also sent to the caregiver web app (over MQTT and "
            "secure WebSockets)."
        )
