"""System status: real readings from the machine running the demo."""

from __future__ import annotations

import psutil
import streamlit as st
import torch

from app.components.cards import render_page_header
from app.core.backend import get_backend
from app.core.inference_runner import load_frozen_fall_model, load_pose_model


def render_telemetry_view() -> None:
    """Hardware, model and pipeline status for this demo instance."""
    render_page_header(
        "System status",
        "Live readings from the computer running this demo, and which parts of the pipeline "
        "are switched on.",
    )

    st.subheader("This computer")
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    backend = get_backend()
    disk = psutil.disk_usage(str(backend.data_dir))
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CPU load", f"{cpu:.0f}%", border=True)
    c2.metric(
        "Memory in use",
        f"{ram.percent:.0f}%",
        f"{ram.used / 1024**3:.1f} of {ram.total / 1024**3:.1f} GB",
        delta_color="off",
        delta_arrow="off",
        border=True,
    )
    c3.metric(
        "Runs on",
        "GPU" if gpu else "CPU",
        gpu[:28] if gpu else "No CUDA GPU found",
        delta_color="off",
        delta_arrow="off",
        border=True,
    )
    c4.metric("Free disk for snapshots", f"{disk.free / 1024**3:.0f} GB", border=True)

    st.subheader("Pipeline")
    rows = [
        ("Pose model (YOLO26s-Pose)", load_pose_model() is not None, "models/yolo26s-pose.pt"),
        (
            "Fall classifier (frozen V6.3)",
            load_frozen_fall_model() is not None,
            "models/v6_3_phase3b/",
        ),
        ("Incident store", True, f"{backend.data_dir.name}/eldercare_demo.db"),
        ("AI second opinion", backend.vlm_enabled, backend.vlm_label),
    ]
    with st.container(border=True):
        for name, on, detail in rows:
            left, right = st.columns([0.4, 0.6])
            with left:
                st.badge(
                    f"{name}: {'on' if on else 'off'}",
                    color="green" if on else "gray",
                    icon=":material/check_circle:" if on else ":material/radio_button_unchecked:",
                )
            right.caption(detail)
    st.caption(
        "The production service also publishes alerts over MQTT and WebSocket; this demo "
        "runs standalone and does not."
    )
