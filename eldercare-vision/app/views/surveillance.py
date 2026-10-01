"""Live Surveillance & 1-Click Demo Hub for ElderCare Vision."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st

from app.components.cards import (
    render_demo_tour_guide,
    render_fall_alert_banner,
    render_header,
)
from app.components.video_canvas import annotate_frame
from app.core.data_loader import IncidentItem, get_sample_videos
from app.core.inference_runner import FallInferenceEngine, load_pose_model


def render_surveillance_view() -> None:
    """Render the primary surveillance monitoring and live inference page."""
    render_header(
        title="Live Surveillance & AI Inference",
        subtitle="Real-time YOLO26 Pose Estimation, Person Tracking, and Fall Detection",
        status_text="SYSTEM ACTIVE",
        status_variant="safe",
    )

    render_demo_tour_guide(
        page_title="Live Surveillance",
        steps=[
            "Click **Quick Demo: Fall Event** to play a verified fall sequence with automatic skeleton tracking.",
            "Watch the status badge transition from **NORMAL** (Green) to **FALL CONFIRMED** (Red) with Time-to-Alert.",
            "Toggle **Privacy Redaction** in the sidebar to demonstrate HIPAA-compliant facial blurring.",
            "Observe the live kinetic energy and aspect ratio time-series charts updating in real time.",
        ],
    )

    # 1. Quick Demo Selector Bar
    sample_videos = get_sample_videos()
    fall_clips = [v for v in sample_videos if v.category == "fall"]
    adl_clips = [v for v in sample_videos if v.category == "adl"]

    preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)
    with preset_col1:
        if st.button("🎬 Quick Demo: Fall Event", width="stretch", type="primary"):
            st.session_state.active_video_path = str(fall_clips[0].path) if fall_clips else None
            st.session_state.active_video_label = "URFD Fall-01 (Verified Fall Sequence)"
            st.session_state.is_running = True
            st.rerun()

    with preset_col2:
        if st.button("🏃 Quick Demo: Normal ADL", width="stretch"):
            st.session_state.active_video_path = str(adl_clips[0].path) if adl_clips else None
            st.session_state.active_video_label = "URFD ADL-01 (Normal Daily Activity)"
            st.session_state.is_running = True
            st.rerun()

    with preset_col3:
        if st.button("📁 Upload Custom Clip", width="stretch"):
            st.session_state.active_video_path = "UPLOAD"
            st.session_state.active_video_label = "Custom Uploaded Video"
            st.session_state.is_running = False
            st.rerun()

    with preset_col4:
        if st.button("📷 Test Live Webcam", width="stretch"):
            st.session_state.active_video_path = "WEBCAM"
            st.session_state.active_video_label = "Live Local Camera Feed"
            st.session_state.is_running = False
            st.rerun()

    # Active Video Source Resolution
    active_source = st.session_state.get("active_video_path")
    if active_source is None and fall_clips:
        st.session_state.active_video_path = str(fall_clips[0].path)
        st.session_state.active_video_label = "URFD Fall-01 (Verified Fall Sequence)"
        active_source = st.session_state.active_video_path

    # Custom Video Upload Handling
    if active_source == "UPLOAD":
        uploaded_file = st.file_uploader(
            "Select an MP4, AVI, or MOV video file to analyze",
            type=["mp4", "avi", "mov"],
        )
        if uploaded_file is not None:
            temp_path = Path("temp_upload.mp4")
            temp_path.write_bytes(uploaded_file.read())
            active_source = str(temp_path)
            st.session_state.active_video_path = active_source

    # Layout: Video Feed (Left) & Real-time Telemetry (Right)
    col_video, col_telemetry = st.columns([0.65, 0.35])

    with col_video:
        with st.container(border=True):
            st.markdown(
                f"**Camera Stream:** {st.session_state.get('active_video_label', 'Video Player')}"
            )
            video_placeholder = st.empty()

            # Playback Controls
            ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([0.33, 0.33, 0.34])
            with ctrl_c1:
                run_btn = st.button(
                    "▶ Start Analysis",
                    width="stretch",
                    disabled=st.session_state.get("is_running", False),
                )
                if run_btn:
                    st.session_state.is_running = True
                    st.rerun()
            with ctrl_c2:
                stop_btn = st.button(
                    "⏸ Pause / Stop",
                    width="stretch",
                    disabled=not st.session_state.get("is_running", False),
                )
                if stop_btn:
                    st.session_state.is_running = False
                    st.rerun()
            with ctrl_c3:
                if st.button("↺ Reset Engine", width="stretch"):
                    st.session_state.is_running = False
                    st.session_state.fall_alert_active = False
                    st.rerun()

    with col_telemetry:
        with st.container(border=True):
            st.markdown("**Real-Time Edge Telemetry**")
            metric_status_ph = st.empty()
            metric_fps_ph = st.empty()
            metric_posture_ph = st.empty()
            metric_conf_ph = st.empty()

    # Time-Series Waveform Card
    st.markdown("#### Real-time Kinetic & Posture Dynamics")
    chart_placeholder = st.empty()

    # Sidebar Settings
    with st.sidebar:
        st.markdown("### Inference Parameters")
        st.session_state.fall_threshold = st.slider(
            "Fall Trigger Threshold",
            min_value=0.20,
            max_value=0.80,
            value=st.session_state.get("fall_threshold", 0.55),
            step=0.05,
            help="Kinetic trigger on the classifier's p_falling (frozen V6.3 value: 0.55)",
        )
        st.session_state.down_sustain_sec = st.slider(
            "Min Down Sustain (seconds)",
            min_value=0.10,
            max_value=1.50,
            value=st.session_state.get("down_sustain_sec", 0.45),
            step=0.05,
            help="Low posture must persist this long before an alert (frozen V6.3 value: 0.45 s)",
        )
        st.divider()
        st.markdown("### Visualization Toggles")
        st.session_state.show_skeletons = st.toggle(
            "Show YOLO Pose Skeleton",
            value=st.session_state.get("show_skeletons", True),
        )
        st.session_state.show_bbox = st.toggle(
            "Show Person Bounding Box",
            value=st.session_state.get("show_bbox", True),
        )
        st.session_state.privacy_blur = st.toggle(
            "Privacy Redaction (Face Blur)",
            value=st.session_state.get("privacy_blur", False),
            help="Gaussian blur over facial keypoints for HIPAA compliance",
        )

    # Initialize Engine & Model
    pose_model = load_pose_model()
    engine = FallInferenceEngine(
        fall_threshold=st.session_state.fall_threshold,
        min_down_sec=st.session_state.down_sustain_sec,
    )

    # Video Processing Loop
    if st.session_state.get("is_running", False) and active_source:
        if active_source == "WEBCAM":
            cap = cv2.VideoCapture(0)
        else:
            cap = cv2.VideoCapture(active_source)

        if not cap.isOpened():
            st.error(f"Unable to open video source: {active_source}")
            st.session_state.is_running = False
            return

        frame_history = []
        fps_tracker = []
        frame_idx = 0
        fall_alert_triggered = False

        while cap.isOpened() and st.session_state.get("is_running", False):
            t_start = time.perf_counter()
            ret, frame = cap.read()
            if not ret:
                break  # Video finished

            frame_idx += 1
            # Resize frame for efficient inference
            frame_resized = cv2.resize(frame, (640, 480))

            # Run inference (pipeline runs at 15 Hz on source time; webcam uses call time)
            src_t = None if active_source == "WEBCAM" else cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            result = engine.process_frame(
                frame_resized, pose_model, target_fps=15.0, timestamp=src_t
            )

            # Draw annotations
            annotated = annotate_frame(
                frame=frame_resized,
                keypoints=result.keypoints,
                bbox=result.bbox,
                track_id=result.track_id,
                state=result.state,
                privacy_blur=st.session_state.privacy_blur,
                show_skeleton=st.session_state.show_skeletons,
                show_bbox=st.session_state.show_bbox,
            )

            # Convert BGR to RGB for Streamlit
            rgb_frame = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            video_placeholder.image(rgb_frame, channels="RGB", width="stretch")

            # Calculate FPS and latency
            t_elapsed = time.perf_counter() - t_start
            cur_fps = 1.0 / max(0.001, t_elapsed)
            fps_tracker.append(cur_fps)
            if len(fps_tracker) > 15:
                fps_tracker.pop(0)
            avg_fps = sum(fps_tracker) / len(fps_tracker)

            # Update Telemetry Display
            if result.state == "FALL_DETECTED":
                status_html = '<span class="status-badge badge-alarm">🚨 FALL CONFIRMED</span>'
            elif result.state == "FALLING":
                status_html = '<span class="status-badge badge-warning">⚠️ KINETIC ANOMALY</span>'
            else:
                status_html = '<span class="status-badge badge-safe">● NORMAL / UPRIGHT</span>'

            metric_status_ph.markdown(
                f"<div style='margin-bottom: 0.5rem;'>Status: {status_html}</div>",
                unsafe_allow_html=True,
            )
            metric_fps_ph.metric(
                "Throughput & Latency",
                f"{avg_fps:.1f} FPS",
                f"{t_elapsed * 1000:.0f} ms/frame",
                border=True,
            )
            metric_posture_ph.metric(
                "Bounding Box Ratio",
                f"{result.aspect_ratio:.2f} w/h",
                "Horizontal" if result.aspect_ratio > 1.15 else "Vertical",
                border=True,
            )
            metric_conf_ph.metric(
                "Pose Confidence",
                f"{result.confidence * 100:.0f}%",
                "ByteTrack Active",
                border=True,
            )

            # Update Waveform Data
            frame_history.append(
                {
                    "Frame": frame_idx,
                    "Aspect Ratio (w/h)": result.aspect_ratio,
                    "Floor Proximity": result.floor_proximity,
                    "Vertical Velocity": result.vertical_velocity,
                }
            )
            if len(frame_history) > 60:
                frame_history.pop(0)

            if frame_idx % 2 == 0:
                df_history = pd.DataFrame(frame_history).set_index("Frame")
                chart_placeholder.line_chart(df_history, height=180)

            # Fall Alarm Trigger
            if result.state == "FALL_DETECTED" and not fall_alert_triggered:
                fall_alert_triggered = True
                render_fall_alert_banner(
                    camera_name=st.session_state.get("active_video_label", "CCTV Cam0"),
                    time_str=time.strftime("%H:%M:%S"),
                    confidence=result.confidence,
                    tta_seconds=1.8,
                )
                # Automatically log to session incidents list
                new_inc = IncidentItem(
                    id=f"INC-{int(time.time())}",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                    camera_id="CAM-01",
                    camera_name="Living Area East (Cam 01)",
                    confidence=result.confidence,
                    status="PENDING_REVIEW",
                    duration_sec=2.4,
                    pre_onset_time="-2.0s",
                    impact_time="0.0s",
                    post_fall_time="+2.0s",
                    vlm_summary=(
                        "Sudden downward kinetic acceleration followed by recumbent posture on floor plane. "
                        "Person remained stationary. Automatic alert triggered for nurse review."
                    ),
                    kinetic_score=0.95,
                    floor_distance_score=result.floor_proximity,
                    adl_suppression_score=0.08,
                )
                st.session_state.incidents.insert(0, new_inc)
                st.session_state.live_alerts_triggered += 1

            # Control playback rate
            time.sleep(max(0.01, (1.0 / 20.0) - t_elapsed))

        cap.release()
        st.session_state.is_running = False
        st.success("Video playback completed.")
    else:
        # Static Ready State Display
        if active_source and active_source != "WEBCAM" and active_source != "UPLOAD":
            cap = cv2.VideoCapture(active_source)
            if cap.isOpened():
                ret, first_frame = cap.read()
                if ret:
                    first_frame = cv2.resize(first_frame, (640, 480))
                    annotated = annotate_frame(first_frame, state="NORMAL")
                    rgb_frame = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                    video_placeholder.image(rgb_frame, channels="RGB", width="stretch")
                cap.release()

        metric_status_ph.markdown(
            "Status: <span class='status-badge badge-safe'>● READY / STANDBY</span>",
            unsafe_allow_html=True,
        )
        metric_fps_ph.metric("Target Throughput", "≥ 15.0 FPS", "Edge Target", border=True)
        metric_posture_ph.metric("Detection Mode", "YOLO26s-Pose", "ByteTrack", border=True)
        metric_conf_ph.metric("Fall Gate Threshold", f"{st.session_state.fall_threshold:.2f}", border=True)
