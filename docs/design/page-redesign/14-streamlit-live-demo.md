# 14 — Streamlit live demo view (`live-demo`)

## 1. Purpose and source paths

- Purpose: provide an interactive demonstration workbench to run the frozen temporal fall detector on curated sample clips, user-uploaded videos, or live local webcam input, rendering skeletal overlays, kinematic dynamics, and persisting incident keyframes upon confirmed falls.
- Current sources: [`streamlit_app.py`](../../../streamlit_app.py), [`app/views/surveillance.py`](../../../app/views/surveillance.py), [`app/components/video_canvas.py`](../../../app/components/video_canvas.py), [`app/components/cards.py`](../../../app/components/cards.py), [`app/core/inference_runner.py`](../../../app/core/inference_runner.py), [`app/core/backend.py`](../../../app/core/backend.py), and [`src/eldercare/live/engine.py`](../../../src/eldercare/live/engine.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: Source selection across four modes: `Fall example`, `Everyday activity`, `Your video` (file uploader for MP4/AVI/MOV saved to local disk), and `Webcam` (local device index 0).
- `code-present (runtime unverified)`: Sidebar calibration adjustments: fall trigger threshold (default 0.55), floor posture sustain duration (default 0.45 s), toggle skeletons (17 keypoints), toggle bounding box, and face region blur for privacy.
- `code-present (runtime unverified)`: Stream lifecycle control: Start Stream, Stop Stream, live indicator badge, and automated loop processing at target playback FPS.
- `code-present (runtime unverified)`: Video canvas annotation (`annotate_frame`) showing keypoint skeleton bones, bounding boxes, state labels, and face anonymization blur.
- `code-present (runtime unverified)`: Real-time kinematic readout: current temporal state (`NORMAL`, `LOSING_BALANCE`, `FALLING`, `ON_FLOOR`, `NO_PERSON`, `IDLE`), posterior fall likelihood percentage, and playback time.
- `code-present (runtime unverified)`: Rolling kinematic dynamics chart (4-second sliding window) plotting Fall Likelihood and normalized Hip Height over time.
- `code-present (runtime unverified)`: Automated incident persistence: confirmed fall event triggers SQLite record creation and saves 3 synchronized keyframes (-3.0 s, -1.5 s, alert onset) to local evidence directory.
- `partial`: Video streaming uses a Streamlit script loop with `time.sleep` and `st.empty` image swapping; high-load scenarios may experience frame pacing jitter on CPU or low-end GPUs.
- `partial`: Webcam mode operates directly on local host device index 0; remote browser clients cannot transmit their camera feed to this Streamlit instance without WebRTC.
- `absent`: RTSP camera stream ingest selector, multi-stream parallel views, hardware video decoding selection, and automated cloud notification webhooks.

## 3. Proposed hierarchy

1. View Header: Title `Live Inference Demo`, real-time monitoring eyebrow, Local Engine badge, and concise operational instructions.
2. Source Configuration Bar: Segmented control for video sources (`Fall example`, `Everyday activity`, `Your video`, `Webcam`) with clip selection dropdown or upload dropzone.
3. Stream Action Controls: `Start Stream` (primary cobalt button), `Stop Stream`, and active pipeline indicator badge.
4. Primary Split View:
   - Left (62% width): Annotated video viewport showing resolution/stream label, followed by the rolling 4-second Kinematic Dynamics line chart (Fall Likelihood vs Hip Height).
   - Right (38% width): Live Telemetry panel containing state badge, Posterior Fall Likelihood metric card, playback timestamp, session alert counter, and instant link to inspect registered incidents.
5. Post-Stream Summary: Completion alert detailing total registered fall events and one-click navigation to the Incidents queue.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  Streamlit Shell [Sidebar: Thresholds · Overlays · Privacy blur]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Live Inference Demo      REAL-TIME MONITORING · EDGE INFERENCE [Local Engine]│
│ [Video Source: (Fall example) | Everyday activity | Your video | Webcam    ] │
│ Clip Selector: [URFD Fall 01 - Forward fall onto mat               ▼]        │
│ [Start Stream] [Stop Stream]   ● Pipeline Running (20 FPS)                   │
├─────────────────────────────────────────┬────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │ ┌────────────────────────────────┐ │
│ │ Viewport: URFD Fall 01 (640×480)    │ │ │ LIVE TELEMETRY                 │ │
│ │ [Annotated Video Feed: Skeleton     │ │ │ State: [ ON_FLOOR ] (Red)      │ │
│ │  + Bounding Box + Face Blur]        │ │ │ Posterior Fall Likelihood: 94% │ │
│ │                                     │ │ │ Playback Time: 3.42s           │ │
│ └─────────────────────────────────────┘ │ ├────────────────────────────────┤ │
│ ┌─────────────────────────────────────┐ │ │ Alerts This Session: 1         │ │
│ │ Kinematic Dynamics (Rolling 4s)     │ │ │ [Review Recent Incident ->]    │ │
│ │ [Chart: Fall Likelihood vs Hip Ht]  │ │ └────────────────────────────────┘ │
│ └─────────────────────────────────────┘ │                                    │
└─────────────────────────────────────────┴────────────────────────────────────┘

390 × 844  Streamlit Mobile
[Menu] Live Demo [Local Engine]
[Source: Fall | ADL | Upload | Cam]
[Start Stream] [Stop Stream]
[Video Viewport: Annotated Feed]
[State: ON_FLOOR] [Likelihood: 94%]
[Kinematic Chart 4s Window]
[Session Alerts: 1] [Review ->]
```

## 5. Controls and states

- Controls: Video source selector, sample clip selectbox, file uploader, Start/Stop buttons, sidebar threshold sliders and toggle switches.
- Idle State: Displays sample poster image or camera placeholder; readout shows `IDLE` state with `–` likelihood; status caption invites user to start stream.
- Streaming Active: Video updates frame-by-frame; readout dynamically shifts from `NORMAL` to `LOSING_BALANCE` to `FALLING` to `ON_FLOOR`; line chart draws rolling trajectory.
- Fall Alert Triggered: Red alert banner renders beneath telemetry; SQLite incident created; session counter increments; direct link to review incident appears.
- Stream Finished: Success banner summarizes detected events (`Run completed. 1 fall event(s) registered for review`) with button linking to the review queue.
- Model Missing Warning: If weights are absent, displays an amber caution banner and executes video playback in pass-through mode without inference.

## 6. Responsive and accessibility rules

- At 390px, stack the video viewport above the live telemetry panel and chart; ensure Start/Stop controls span full width for accessible touch interaction.
- Use explicit semantic text for all temporal states (`NORMAL`, `LOSING_BALANCE`, `FALLING`, `ON_FLOOR`) rather than color coding alone.
- Maintain high contrast on all annotated bounding boxes, keypoint circles, and telemetry readout cards.
- Respect prefers-reduced-motion by allowing users to toggle off skeleton rendering and chart animations.

## 7. Synthetic image prompt

```text
Design a synthetic Streamlit live inference demonstration reference for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white cards with crisp borders, no translucent glass blur or 3D art. Show a Streamlit sidebar with detector threshold sliders (0.55 fall trigger, 0.45s floor posture) and display toggles. Top controls feature video source segmented buttons (Fall example selected) and a bold cobalt Start Stream button with an active green status pill. Left pane shows a crisp 640x480 video viewport featuring an annotated stylized stick-figure skeleton on floor posture with blurred head region and bounding box, followed by a clean 2-line chart showing kinematic fall likelihood surging as hip height drops. Right pane displays a solid telemetry panel with a red “ON_FLOOR” state pill, a 94% Posterior Fall Likelihood metric card, playback timestamp 3.42s, and an alert card reading “Confirmed fall detected: Incident registered”. Desktop 1440x1000; mobile 390x844 stacks video and readout. Synthetic demonstration graphics only, no real patient photos, no code.
```
