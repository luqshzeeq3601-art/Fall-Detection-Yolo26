"""Live demo: run the frozen fall detector on a sample clip, an upload or a webcam."""

from __future__ import annotations

import re
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from app.components.cards import (
    render_live_indicator,
    render_page_header,
    render_section_header,
    render_status_badge,
)
from app.components.video_canvas import annotate_frame
from app.core.backend import KEYFRAME_OFFSETS_SEC, get_backend
from app.core.data_loader import get_sample_videos
from app.core.inference_runner import (
    FallInferenceEngine,
    FrameInferenceResult,
    frozen_operating_point,
    load_frozen_fall_model,
    load_pose_model,
)
from app.core.nav import page_link
from eldercare.common.redaction import redact_rtsp_url

FRAME_SIZE = (640, 480)
PLAYBACK_FPS = 20.0
CHART_WINDOW = 80  # ~4 s of frames at playback rate
SOURCE_KINDS = ("Fall example", "Everyday activity", "Your video", "Webcam", "RTSP stream")


def _sidebar_settings() -> None:
    st.sidebar.html('<div class="sidebar-group">Live Demo settings</div>')
    op = frozen_operating_point()
    default_threshold = op.get("fall_trigger_threshold", 0.55)
    default_sustain = op.get("min_down_sustain_seconds", 0.45)

    def _reset() -> None:
        st.session_state.fall_threshold = st.session_state.w_fall_threshold = default_threshold
        st.session_state.down_sustain_sec = st.session_state.w_down_sustain_sec = default_sustain

    # Streamlit drops widget state while another page is shown, so re-seed the
    # slider keys from the persistent values when coming back to this page.
    st.session_state.setdefault("w_fall_threshold", st.session_state.fall_threshold)
    st.session_state.setdefault("w_down_sustain_sec", st.session_state.down_sustain_sec)

    with st.sidebar.expander("Detector settings", icon=":material/tune:"):
        st.session_state.fall_threshold = st.slider(
            "Alert sensitivity",
            0.20,
            0.80,
            step=0.05,
            key="w_fall_threshold",
            help="Fall score needed to start an alert. Lower catches more falls but gives "
            f"more false alarms. Default: {default_threshold:.2f}.",
        )
        st.session_state.down_sustain_sec = st.slider(
            "Time on the floor before alert (s)",
            0.10,
            1.50,
            step=0.05,
            key="w_down_sustain_sec",
            help="How long the person must stay low after the drop. "
            f"Default: {default_sustain:.2f} s.",
        )
        st.session_state.show_skeletons = st.toggle(
            "Show body points", value=st.session_state.show_skeletons
        )
        st.session_state.show_bbox = st.toggle("Show person box", value=st.session_state.show_bbox)
        st.session_state.privacy_blur = st.toggle(
            "Blur faces",
            value=st.session_state.privacy_blur,
            help="Blurs faces in the video shown on screen.",
        )
        st.button(
            "Reset to defaults", icon=":material/restart_alt:", width="stretch", on_click=_reset
        )


def _pick_source() -> tuple[str | None, str]:
    """Return (video path, 'WEBCAM' or None; human-readable label)."""
    kind = st.segmented_control(
        "1. Choose a video", SOURCE_KINDS, default=SOURCE_KINDS[0], key="source_kind"
    )
    kind = kind or SOURCE_KINDS[0]
    clips = get_sample_videos()

    if kind in ("Fall example", "Everyday activity"):
        category = "fall" if kind == "Fall example" else "adl"
        options = [c for c in clips if c.category == category]
        if not options:
            st.warning(
                "No sample clips found on this computer. Add URFD videos to "
                "`datasets/raw/urfd/`, or choose **Your video** to upload one.",
                icon=":material/warning:",
            )
            return None, kind
        clip = st.selectbox("Clip", options, format_func=lambda c: c.name, key=f"clip_{category}")
        st.caption(clip.description)
        return str(clip.path), clip.name

    if kind == "Your video":
        uploaded = st.file_uploader("Upload a video (MP4, AVI or MOV)", type=["mp4", "avi", "mov"])
        if uploaded is None:
            return None, kind
        target = get_backend().data_dir / "uploads" / Path(uploaded.name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(uploaded.getvalue())
        return str(target), uploaded.name

    if kind == "RTSP stream":
        rtsp_input = st.text_input(
            "RTSP Camera URL",
            placeholder="rtsp://192.168.1.100:8080/h264_pcm.sdp",
            help="Direct stream from IP camera, phone camera app, or test stream. Credentials are automatically redacted.",
            key="rtsp_url_input",
        )
        if not rtsp_input or not rtsp_input.strip():
            st.info("Enter an RTSP stream URL to connect (e.g. from an IP camera or phone broadcast app).", icon=":material/info:")
            return None, kind
        clean_url = rtsp_input.strip()
        redacted = redact_rtsp_url(clean_url)
        st.caption(f"Target feed: `{redacted}`")
        return clean_url, f"RTSP: {redacted}"

    st.caption("Uses this computer's camera. Frames are checked in memory and not saved.")
    return "WEBCAM", "Webcam"


def _camera_id(label: str) -> str:
    return ("demo-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"))[:64]


def _pick_keyframes(buffer: deque[tuple[float, np.ndarray]], now: float) -> list[np.ndarray]:
    """Frames closest to each KEYFRAME_OFFSETS_SEC before ``now`` (alert frame first)."""
    if not buffer:
        return []
    return [min(buffer, key=lambda tf: abs(tf[0] - (now - off)))[1] for off in KEYFRAME_OFFSETS_SEC]


def _render_readout(result: FrameInferenceResult | None, video_time: float | None) -> None:
    if result is None:
        render_status_badge("IDLE")
    else:
        render_status_badge(result.state if result.track_id >= 0 else "NO_PERSON")

    likelihood = "-"
    if result is not None and result.track_id >= 0:
        p_fall = result.confidence if result.state != "NORMAL" else 1.0 - result.confidence
        likelihood = f"{p_fall * 100:.0f}%"

    st.metric(
        "Fall likelihood",
        likelihood,
        help="How sure the model is, right now, that the person is falling or has fallen.",
        border=True,
    )
    if video_time is not None:
        st.caption(f"Video time: {video_time:.1f} s")


def _render_session_count(ph: DeltaGenerator) -> None:
    with ph.container():
        st.metric(
            "Falls detected this session",
            st.session_state.alerts_this_session,
            border=True,
        )
        if st.session_state.last_incident_id:
            page_link("incidents", "Review the latest fall", ":material/arrow_forward:")


def render_surveillance_view() -> None:
    """Live demo surveillance page."""
    render_page_header(
        title="Live Demo",
        intro=(
            "Choose a video, press Start, and watch the detector at work. The status panel "
            "shows what it sees. Confirmed falls are saved to Incidents & Review."
        ),
        badge_text="Runs locally",
        badge_color="green",
        badge_icon=":material/memory:",
    )
    _sidebar_settings()

    with st.container(border=True):
        source, label = _pick_source()

    if st.session_state.get("active_source") != source:
        st.session_state.active_source = source
        st.session_state.is_running = False

    is_active = st.session_state.get("is_running", False)

    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button(
            "Start",
            type="primary",
            icon=":material/play_arrow:",
            disabled=source is None or is_active,
        ):
            st.session_state.is_running = True
            st.rerun()

        if st.button(
            "Stop",
            icon=":material/stop:",
            disabled=not is_active,
        ):
            st.session_state.is_running = False
            st.rerun()

        if is_active:
            render_live_indicator("Running. Press Stop to end.", active=True)
        elif source is None:
            st.caption("Choose a clip, upload a video, or pick the webcam to begin.")
        else:
            render_live_indicator("2. Press Start to run the detector.", active=False)

    pose_model = load_pose_model()
    if pose_model is None or load_frozen_fall_model() is None:
        st.warning(
            "Detector model files are missing (`models/yolo26s-pose.pt` or "
            "`models/v6_3_phase3b/`). The video will play, but falls will not be detected.",
            icon=":material/warning:",
        )

    col_video, col_side = st.columns([0.62, 0.38])
    with col_video:
        with st.container(border=True):
            st.markdown(f"**:material/videocam: {label}**")
            video_ph = st.empty()

        render_section_header(
            title="Last 4 seconds",
            subtitle="Fall likelihood rises when hip height drops quickly toward the floor.",
            icon=":material/show_chart:",
        )
        chart_ph = st.empty()

    with col_side, st.container(border=True):
        st.markdown("**:material/monitor_heart: What the detector sees**")
        readout_ph = st.empty()
        alert_ph = st.empty()
        st.divider()
        session_ph = st.empty()
        _render_session_count(session_ph)

    if st.session_state.get("is_running") and source:
        _run(source, label, pose_model, video_ph, chart_ph, readout_ph, alert_ph, session_ph)
        return

    with readout_ph.container():
        _render_readout(None, None)

    is_rtsp = bool(source and source.lower().startswith(("rtsp://", "rtsps://")))
    if source and source != "WEBCAM" and not is_rtsp:
        cap = cv2.VideoCapture(source)
        ok, frame = cap.read()
        cap.release()
        if ok:
            frame = cv2.resize(frame, FRAME_SIZE)
            video_ph.image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), width="stretch")


def _run(
    source: str,
    label: str,
    pose_model: object,
    video_ph: DeltaGenerator,
    chart_ph: DeltaGenerator,
    readout_ph: DeltaGenerator,
    alert_ph: DeltaGenerator,
    session_ph: DeltaGenerator,
) -> None:
    is_live = source == "WEBCAM" or source.lower().startswith(("rtsp://", "rtsps://"))
    cap = cv2.VideoCapture(0 if source == "WEBCAM" else source)
    if not cap.isOpened():
        st.error(
            "Could not open this video or RTSP stream. Check camera network connectivity and URL.",
            icon=":material/error:",
        )
        st.session_state.is_running = False
        return

    engine = FallInferenceEngine(
        fall_threshold=st.session_state.fall_threshold,
        min_down_sec=st.session_state.down_sustain_sec,
    )
    keep = int(max(KEYFRAME_OFFSETS_SEC) * PLAYBACK_FPS) + 10
    frames: deque[tuple[float, np.ndarray]] = deque(maxlen=keep)
    history: deque[dict[str, float]] = deque(maxlen=CHART_WINDOW)
    falls_here = 0
    frame_idx = 0
    t0 = time.perf_counter()

    while cap.isOpened() and st.session_state.get("is_running", False):
        t_start = time.perf_counter()
        ok, raw = cap.read()
        if not ok:
            break
        frame_idx += 1
        frame = cv2.resize(raw, FRAME_SIZE)
        src_t = (t_start - t0) if is_live else cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        frames.append((src_t, frame))
        result = engine.process_frame(
            frame, pose_model, target_fps=15.0, timestamp=None if is_live else src_t
        )

        shown = annotate_frame(
            frame=frame,
            keypoints=result.keypoints,
            bbox=result.bbox,
            track_id=result.track_id,
            state=result.state,
            privacy_blur=st.session_state.privacy_blur,
            show_skeleton=st.session_state.show_skeletons,
            show_bbox=st.session_state.show_bbox,
        )
        video_ph.image(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB), width="stretch")

        with readout_ph.container():
            _render_readout(result, src_t)

        if result.track_id >= 0:
            p_fall = result.confidence if result.state != "NORMAL" else 1.0 - result.confidence
            history.append(
                {
                    "Time (s)": round(src_t, 2),
                    "Fall Likelihood": p_fall,
                    "Hip Height": 1.0 - result.floor_proximity,
                }
            )
        if len(history) > 1 and frame_idx % 2 == 0:
            chart_ph.line_chart(pd.DataFrame(history).set_index("Time (s)"), height=200)

        if result.fall_event is not None:
            falls_here += 1
            try:
                incident_id = get_backend().record_fall(
                    result.fall_event, _camera_id(label), _pick_keyframes(frames, src_t)
                )
                st.session_state.alerts_this_session += 1
                st.session_state.last_incident_id = incident_id
                _render_session_count(session_ph)
                alert_ph.error(
                    f"Fall detected at {src_t:.1f} s. Saved as incident #{incident_id[:8]} "
                    f"with {len(KEYFRAME_OFFSETS_SEC)} snapshots for review.",
                    icon=":material/emergency:",
                )
            except Exception as exc:
                alert_ph.error(
                    f"Fall detected at {src_t:.1f} s, but it could not be saved: {exc}",
                    icon=":material/error:",
                )

        if is_live:
            time.sleep(0.001)
        else:
            time.sleep(max(0.0, 1.0 / PLAYBACK_FPS - (time.perf_counter() - t_start)))

    cap.release()
    st.session_state.is_running = False
    if falls_here:
        st.success(
            f"Finished. {falls_here} fall{'s' if falls_here != 1 else ''} saved for review.",
            icon=":material/task_alt:",
        )
        page_link("incidents", "Open Incidents & Review", ":material/arrow_forward:")
    else:
        st.info("Finished. No falls detected in this video.", icon=":material/check_circle:")
