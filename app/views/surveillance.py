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

from app.components.cards import render_page_header, render_status_badge
from app.components.video_canvas import annotate_frame
from app.core.backend import KEYFRAME_OFFSETS_SEC, get_backend
from app.core.data_loader import get_sample_videos
from app.core.inference_runner import (
    FallInferenceEngine,
    FrameInferenceResult,
    load_frozen_fall_model,
    load_pose_model,
)
from app.core.nav import page_link

FRAME_SIZE = (640, 480)
PLAYBACK_FPS = 20.0
CHART_WINDOW = 80  # ~4 s of frames at playback rate
SOURCE_KINDS = ("Fall example", "Everyday activity", "Your video", "Webcam")


def _sidebar_settings() -> None:
    with st.sidebar.expander("Advanced settings", icon=":material/tune:"):
        st.session_state.fall_threshold = st.slider(
            "Fall trigger threshold",
            0.20,
            0.80,
            value=st.session_state.fall_threshold,
            step=0.05,
            help="How sure the model must be that a fall is starting. Frozen model: 0.55.",
        )
        st.session_state.down_sustain_sec = st.slider(
            "Seconds the person must stay down",
            0.10,
            1.50,
            value=st.session_state.down_sustain_sec,
            step=0.05,
            help="Low posture must last this long before an alert. Frozen model: 0.45 s.",
        )
        st.session_state.show_skeletons = st.toggle(
            "Show body points", value=st.session_state.show_skeletons
        )
        st.session_state.show_bbox = st.toggle("Show person box", value=st.session_state.show_bbox)
        st.session_state.privacy_blur = st.toggle(
            "Blur head area on screen",
            value=st.session_state.privacy_blur,
            help="Blurs the top of each person box in the displayed video.",
        )


def _pick_source() -> tuple[str | None, str]:
    """Return (video path, "WEBCAM" or None; human-readable label)."""
    kind = st.segmented_control(
        "Video source", SOURCE_KINDS, default=SOURCE_KINDS[0], key="source_kind"
    )
    kind = kind or SOURCE_KINDS[0]
    clips = get_sample_videos()

    if kind in ("Fall example", "Everyday activity"):
        category = "fall" if kind == "Fall example" else "adl"
        options = [c for c in clips if c.category == category]
        if not options:
            st.warning(
                "Sample clips are not installed. Put the URFD videos in `datasets/raw/urfd/` "
                "or choose **Your video**."
            )
            return None, kind
        clip = st.selectbox("Clip", options, format_func=lambda c: c.name, key=f"clip_{category}")
        st.caption(clip.description)
        return str(clip.path), clip.name

    if kind == "Your video":
        uploaded = st.file_uploader("Upload a video", type=["mp4", "avi", "mov"])
        if uploaded is None:
            return None, kind
        target = get_backend().data_dir / "uploads" / Path(uploaded.name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(uploaded.getvalue())
        return str(target), uploaded.name

    st.caption("Uses this computer's camera. Video stays on this machine.")
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

    likelihood = "–"
    if result is not None and result.track_id >= 0:
        p_fall = result.confidence if result.state != "NORMAL" else 1.0 - result.confidence
        likelihood = f"{p_fall * 100:.0f}%"
    st.metric(
        "Fall likelihood",
        likelihood,
        help="The model's estimate that the person in view is falling or has fallen.",
    )
    if video_time is not None:
        st.caption(f"Video time {video_time:.1f} s")


def _render_session_count(ph: DeltaGenerator) -> None:
    with ph.container():
        st.metric("Falls detected this session", st.session_state.alerts_this_session)
        if st.session_state.last_incident_id:
            page_link("incidents", "Review the latest incident", ":material/arrow_forward:")


def render_surveillance_view() -> None:
    """Live demo page."""
    render_page_header(
        "Live demo",
        "Pick a video and press Start. The overlay shows the body points the pose model finds; "
        "the panel on the right shows what the fall detector has decided. Every detected fall "
        "is saved as an incident you can review.",
    )
    _sidebar_settings()

    source, label = _pick_source()
    if st.session_state.get("active_source") != source:
        st.session_state.active_source = source
        st.session_state.is_running = False

    with st.container(horizontal=True):
        if st.button(
            "Start",
            type="primary",
            icon=":material/play_arrow:",
            disabled=source is None or st.session_state.get("is_running", False),
        ):
            st.session_state.is_running = True
            st.rerun()
        if st.button(
            "Stop", icon=":material/stop:", disabled=not st.session_state.get("is_running", False)
        ):
            st.session_state.is_running = False
            st.rerun()

    pose_model = load_pose_model()
    if pose_model is None or load_frozen_fall_model() is None:
        st.warning(
            "Model weights are missing (`models/yolo26s-pose.pt` and `models/v6_3_phase3b/`), "
            "so the video plays without detection."
        )

    col_video, col_side = st.columns([0.6, 0.4])
    with col_video:
        video_ph = st.empty()
        st.markdown("**Last 4 seconds**")
        chart_ph = st.empty()
        st.caption(
            "A fall shows as the fall likelihood jumping up while hip height drops and stays low."
        )
    with col_side, st.container(border=True):
        st.markdown("**What the detector sees**")
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
    if source and source != "WEBCAM":
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
    cap = cv2.VideoCapture(0 if source == "WEBCAM" else source)
    if not cap.isOpened():
        st.error("Could not open this video. Try another file or source.")
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
        src_t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 if source != "WEBCAM" else t_start - t0
        frames.append((src_t, frame))
        result = engine.process_frame(
            frame, pose_model, target_fps=15.0, timestamp=None if source == "WEBCAM" else src_t
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
                    "Fall likelihood": p_fall,
                    "Hip height in frame": 1.0 - result.floor_proximity,
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
                    f"Fall detected at {src_t:.1f} s. Saved as an incident with "
                    f"{len(KEYFRAME_OFFSETS_SEC)} snapshots for review.",
                    icon=":material/emergency:",
                )
            except Exception as exc:  # keep playback going; the alert is still shown
                alert_ph.error(f"Fall detected at {src_t:.1f} s, but saving failed: {exc}")

        time.sleep(max(0.0, 1.0 / PLAYBACK_FPS - (time.perf_counter() - t_start)))

    cap.release()
    st.session_state.is_running = False
    if falls_here:
        st.success(
            f"Finished. {falls_here} fall(s) detected and saved.", icon=":material/task_alt:"
        )
        page_link("incidents", "Review them now", ":material/arrow_forward:")
    else:
        st.info("Finished. No fall was detected in this video.", icon=":material/check_circle:")
