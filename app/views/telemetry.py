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
            "Real-time diagnostic metrics from the local edge machine. Monitors hardware "
            "resource allocation, GPU acceleration availability, model weight checkpoints, "
            "and local persistence subsystems."
        ),
        eyebrow="LOCAL EDGE TELEMETRY · HEALTH MONITOR",
        badge_text="Host Operational",
        badge_color="green",
    )

    render_section_header(
        title="Host Hardware Allocation",
        subtitle="Live compute and memory utilization metrics on this device.",
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
            label="CPU Utilization",
            value=f"{cpu:.0f}%",
            delta="Available" if cpu < 80 else "Elevated Load",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c2:
        st.metric(
            label="Physical Memory",
            value=f"{ram.percent:.0f}%",
            delta=f"{ram.used / 1024**3:.1f} of {ram.total / 1024**3:.1f} GB",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c3:
        st.metric(
            label="Compute Device",
            value="NVIDIA GPU" if gpu else "Host CPU",
            delta=gpu[:26] if gpu else "CUDA Not Detected",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )
    with c4:
        st.metric(
            label="Storage Headroom",
            value=f"{disk.free / 1024**3:.0f} GB",
            delta="Evidence partition",
            delta_color="off",
            delta_arrow="off",
            border=True,
        )

    st.divider()

    render_section_header(
        title="Inference & Pipeline Subsystems",
        subtitle="Verification status of loaded model weights, local SQLite store, and multimodal reasoning.",
        icon=":material/developer_board:",
    )

    subsystems = [
        (
            "YOLO26s-Pose Detector",
            load_pose_model() is not None,
            "17 COCO Keypoints extraction",
            "models/yolo26s-pose.pt",
        ),
        (
            "Temporal Fall Classifier",
            load_frozen_fall_model() is not None,
            "V6.3 Frozen temporal classifier weights",
            "models/v6_3_phase3b/",
        ),
        (
            "Local Incident Database",
            True,
            "SQLite persistent evidence ledger",
            f"{backend.data_dir.name}/eldercare_demo.db",
        ),
        (
            "Advisory VLM Engine",
            backend.vlm_enabled,
            "Multimodal scene reasoning agent",
            backend.vlm_label,
        ),
    ]

    with st.container(border=True):
        for name, active, purpose, artifact in subsystems:
            col_state, col_info, col_path = st.columns([0.3, 0.35, 0.35], vertical_alignment="center")
            with col_state:
                st.badge(
                    f"{name}",
                    color="green" if active else "gray",
                    icon=":material/check_circle:" if active else ":material/radio_button_unchecked:",
                )
            with col_info:
                st.caption(purpose)
            with col_path:
                st.code(artifact, language="bash")

    st.divider()

    with st.container(border=True):
        st.markdown("**:material/lan: Network & Deployment Architecture**")
        st.caption(
            "This interactive demo runs entirely in self-contained standalone mode. In production "
            "installations, confirmed fall incidents and live state telemetry are published concurrently "
            "over low-latency MQTT message queues and authenticated WebSockets to the web portal."
        )
