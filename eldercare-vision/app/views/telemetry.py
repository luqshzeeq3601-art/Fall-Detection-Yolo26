"""Edge System Health & IoT Fleet Observability for ElderCare Vision."""

from __future__ import annotations

import datetime

import psutil
import streamlit as st
import torch

from app.components.cards import render_demo_tour_guide, render_header


def render_telemetry_view() -> None:
    """Render the edge telemetry and system health monitor."""
    render_header(
        title="Edge System Health & IoT Fleet Monitor",
        subtitle="Hardware Resource Utilization, RTSP Resilience & MQTT Telemetry",
        status_text="ALL SERVICES HEALTHY",
        status_variant="safe",
    )

    render_demo_tour_guide(
        page_title="System Telemetry",
        steps=[
            "Monitor live **Edge Device Hardware Load** (CPU, RAM, GPU acceleration, and storage).",
            "Verify **CCTV Stream Resilience** metrics (uptime, automatic reconnect times, and dropped frame rates).",
            "Inspect **MQTT Message Broker Status** for real-time IoT alert dispatching.",
            "Review the centralized **Edge System Event Audit Log**.",
        ],
    )

    # 1. Hardware Resource Utilization
    st.markdown("### Edge Device Hardware Utilization")

    cpu_pct = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_pct = ram.percent
    disk = psutil.disk_usage(".")
    disk_free_gb = disk.free / (1024**3)

    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else "CPU Native Mode (Optimized)"

    hw1, hw2, hw3, hw4 = st.columns(4)
    with hw1:
        st.metric(
            label="CPU Utilization",
            value=f"{cpu_pct:.1f}%",
            delta="Normal Load (<60%)" if cpu_pct < 60 else "Elevated Load",
            border=True,
        )
    with hw2:
        st.metric(
            label="RAM Utilization",
            value=f"{ram_pct:.1f}%",
            delta=f"{(ram.used / (1024**3)):.1f} / {(ram.total / (1024**3)):.1f} GB",
            delta_color="off",
            border=True,
        )
    with hw3:
        st.metric(
            label="Acceleration Device",
            value="CUDA Enabled" if gpu_available else "CPU Fast Path",
            delta=gpu_name[:22],
            delta_color="normal" if gpu_available else "off",
            border=True,
        )
    with hw4:
        st.metric(
            label="Evidence Disk Storage",
            value=f"{disk_free_gb:.1f} GB Free",
            delta="Capacity OK",
            delta_color="normal",
            border=True,
        )

    st.divider()

    # 2. CCTV Stream Resilience & MQTT Status
    st.markdown("### CCTV Network Resilience & IoT Pipeline")

    cctv_col, mqtt_col = st.columns(2)

    with cctv_col:
        with st.container(border=True):
            st.markdown("#### CCTV & RTSP Stream Manager")
            st.write("**Active Stream Channels:** `4 / 4 Online`")
            st.write("**Stream Protocol:** `RTSP over TCP / HTTP Fallback`")
            st.write("**Packet Loss / Drop Rate:** `0.02% (Target < 0.5%)`")
            st.write("**Auto-Reconnect Latency:** `140 ms (Target < 500ms)`")
            st.write("**Buffer Health:** `Nominal (Queue Size: 2 frames)`")

    with mqtt_col:
        with st.container(border=True):
            st.markdown("#### MQTT Event Broker & Dispatch")
            st.write("**Broker Connection:** `Connected (localhost:1883)`")
            st.write("**Active Topics:** `eldercare/incidents/alert`, `eldercare/health`")
            st.write("**QoS Level:** `QoS 1 (At least once delivery)`")
            st.write("**Message Publish Latency:** `4.2 ms (p95)`")
            st.write("**Client Heartbeat:** `Acknowledged (30s interval)`")

    st.divider()

    # 3. Live Edge System Log Stream
    st.markdown("### Centralized Edge Event Audit Log")
    log_filter = st.segmented_control(
        "Filter Log Level",
        options=["ALL", "INFO", "WARNING", "ERROR"],
        default="ALL",
        label_visibility="collapsed",
    )

    now = datetime.datetime.now()
    sample_logs = [
        {"timestamp": (now - datetime.timedelta(seconds=2)).strftime("%H:%M:%S.%f")[:-3], "level": "INFO", "source": "pipeline_v6_1", "message": "Inference cycle stable. Track ID #1 active with 17 valid keypoints."},
        {"timestamp": (now - datetime.timedelta(seconds=14)).strftime("%H:%M:%S.%f")[:-3], "level": "INFO", "source": "stream_manager", "message": "RTSP frame buffer synced at 15.0 FPS. No dropped frames detected."},
        {"timestamp": (now - datetime.timedelta(seconds=45)).strftime("%H:%M:%S.%f")[:-3], "level": "WARNING", "source": "adl_suppressor", "message": "Rapid sitting detected on CAM-03; geometric floor proximity rule suppressed false alarm."},
        {"timestamp": (now - datetime.timedelta(minutes=2)).strftime("%H:%M:%S.%f")[:-3], "level": "INFO", "source": "mqtt_publisher", "message": "Published heartbeat telemetry to topic 'eldercare/health'."},
        {"timestamp": (now - datetime.timedelta(minutes=5)).strftime("%H:%M:%S.%f")[:-3], "level": "INFO", "source": "evidence_storage", "message": "Encrypted evidence archive verified. Storage checksums matched."},
    ]

    filtered_logs = sample_logs if log_filter == "ALL" else [entry for entry in sample_logs if entry["level"] == log_filter]

    log_text = "\n".join(
        f"[{log_item['timestamp']}] [{log_item['level']:<7}] [{log_item['source']:<15}] {log_item['message']}"
        for log_item in filtered_logs
    )
    st.code(log_text, language="log")
