# 13 — Streamlit overview view (`overview`)

## 1. Purpose and source paths

- Purpose: serve as the primary entry point and high-impact summary for the standalone Streamlit demonstration, presenting the 4-stage temporal pipeline, verified sealed benchmark scorecard, and system operating boundaries.
- Current sources: [`streamlit_app.py`](../../../streamlit_app.py), [`app/views/overview.py`](../../../app/views/overview.py), [`app/components/cards.py`](../../../app/components/cards.py), [`app/core/backend.py`](../../../app/core/backend.py), [`app/core/data_loader.py`](../../../app/core/data_loader.py), [`app/core/nav.py`](../../../app/core/nav.py), and [`docs/reports/V6_3_FINAL_TESTB_EVALUATION.json`](../../reports/V6_3_FINAL_TESTB_EVALUATION.json).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: Page header with "v6.3 Sealed" badge, intro text, quick-navigation actions to Live Demo, Incident Review, and Benchmark Results.
- `code-present (artifact-backed)`: Sealed Test-B KPI scorecard displaying Verified Recall (98.3%), Verified Precision (96.7%), Median Latency (0.85 s / p95 1.58 s), and held-out Home False Alarms (0.00 / hr over 50 min) read from local JSON report.
- `code-present (runtime unverified)`: Four-stage pipeline overview (Pose Extraction, Temporal Kinematics, Post-Fall Verification, Human-in-the-Loop Audit).
- `code-present (runtime unverified)`: Architecture and operating boundaries container detailing edge privacy, minimalist 3-keyframe evidence retention, local VLM status, and research prototype scope.
- `partial`: Summary copy says "0.00 / hr on 50 min stream" without prominently contextualizing that 0.83 hours of exposure yields a wide Poisson 95% upper bound of 3.59/h; longform longitudinal false alarm rate remains unproven.
- `partial`: Sidebar engine status badge ("Engine Online", "v6.3 Sealed") is statically rendered rather than derived from live model availability or running inference state.
- `absent`: Live video preview on the overview page, direct interactive source selection, user authentication/roles, and multi-camera stream aggregation.

## 3. Proposed hierarchy

1. Page Header: Title `ElderCare Vision`, clear research-prototype eyebrow, V6.3 Sealed status chip, and primary action button `Launch Live Demo` alongside queue/benchmark links.
2. Verified KPI Strip: Four solid cards for Recall (59/60), Precision (59/61), Latency (median 0.85 s, p95 1.58 s), and False Alarm Rate with explicit statistical uncertainty note (`0.83 h evaluated; target unproven`).
3. Four-Stage Pipeline: Step cards for YOLO26s Pose, Temporal Sliding Window, Stability Gate (0.45 s floor posture), and Human-in-the-Loop Audit with 3 keyframes.
4. Operating Boundaries Split: Left panel for Privacy by Design (edge processing, 3-keyframe persistence, local VLM); right panel for Prototype Scope (controlled lab datasets, no medical/life-safety certification).
5. Quick Navigation Footer: Direct routing to Live Demo, Incidents Queue, and System Telemetry.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  Streamlit Shell [Sidebar: Brand · Status · Privacy note]
┌──────────────────────────────────────────────────────────────────────────────┐
│ ElderCare Vision          EDGE AI · TEMPORAL REASONING       [v6.3 Sealed]   │
│ Camera-based fall detection engine. Processes video locally on edge GPU.     │
│ [Launch Live Demo] [Incident Review Queue] [Sealed Benchmark Results]        │
├──────────────────────────────────────────────────────────────────────────────┤
│ BENCHMARK SCORECARD (Sealed UP-Fall Test-B)                                  │
│ [Recall: 98.3% (59/60)] [Precision: 96.7%] [Latency: 0.85s/1.58s] [FA: Unproven] │
├──────────────────────────────────────────────────────────────────────────────┤
│ DETECTION PIPELINE                                                           │
│ [01 Pose Extraction] [02 Kinematics] [03 Stability Gate] [04 Human Audit]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ OPERATING BOUNDARIES                                                         │
│ ┌──────────────────────────────────────┐ ┌─────────────────────────────────┐ │
│ │ Privacy by Design: Local edge GPU,   │ │ Research Prototype: Lab data,   │ │
│ │ 3-keyframe storage, local VLM.       │ │ non-certified, engineering POC. │ │
│ └──────────────────────────────────────┘ └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844  Streamlit Mobile
[Menu] ElderCare Vision [v6.3]
[Launch Live Demo]
[Recall: 98.3%] [Precision: 96.7%]
[Latency: 0.85s] [FA: Unproven]
[Pipeline Steps 01–04 Stacked]
[Privacy Panel]
[Scope & Boundaries Panel]
```

## 5. Controls and states

- Controls: `Launch Live Demo` primary button, `Incident Review Queue` link, `Sealed Benchmark Results` link, sidebar page navigation items.
- Loaded State: Reports loaded successfully; KPI metrics display verified values with source tooltips; pipeline steps display clean step indicators.
- Missing Report State: If `V6_3_FINAL_TESTB_EVALUATION.json` is missing, render an informative alert box (`Evaluation metrics not found in local artifacts`) without zeroing metrics or crashing.
- Live Engine Status: Sidebar badge dynamically indicates whether model files (`yolo26s-pose.pt`, `models/v6_3_phase3b/`) are present on disk.
- Research Boundary Notice: Prominently state prototype boundaries to prevent misunderstanding by non-technical visitors.

## 6. Responsive and accessibility rules

- At 390px, stack the four KPI cards into a 2x2 grid or single column; stack the four pipeline steps vertically; keep `Launch Live Demo` within initial viewport.
- Maintain high contrast between `#142B3C` text and `#FFFFFF` cards against `#F3F7FA` canvas.
- Ensure all metric deltas and badges include accessible text labels rather than relying solely on color indicators.
- Support standard Streamlit keyboard navigation; keep header links tab-accessible.

## 7. Synthetic image prompt

```text
Design a synthetic Streamlit overview dashboard reference for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body at 15/24, proposed IBM Plex Mono for IDs/units at 12/18. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white cards with crisp borders, no translucent glass blur or floating 3D artifacts. Show a clean Streamlit sidebar with branding and local privacy notice. Main viewport displays title “ElderCare Vision” with a v6.3 Sealed badge, three quick-action buttons, four solid metric cards (Recall 98.3%, Precision 96.7%, Latency 0.85 s / p95 1.58 s, and False Alarms labeled “Target unproven”), a four-step horizontal pipeline workflow with numbered cards, and a two-column architecture boundary comparison. Desktop 1440x1000 layout; mobile 390x844 stacks cards cleanly. Synthetic demo data only; no real people, no patient photos, no medical diagnosis claims, no code.
```
