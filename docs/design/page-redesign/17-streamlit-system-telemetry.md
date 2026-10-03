# 17 — Streamlit system telemetry view (`system`)

## 1. Purpose and source paths

- Purpose: provide real-time diagnostic telemetry from the local host executing the Streamlit demo, inspecting hardware resource allocation, GPU acceleration availability, model checkpoint integrity, and local persistence subsystems.
- Current sources: [`streamlit_app.py`](../../../streamlit_app.py), [`app/views/telemetry.py`](../../../app/views/telemetry.py), [`app/components/cards.py`](../../../app/components/cards.py), [`app/core/backend.py`](../../../app/core/backend.py), [`app/core/inference_runner.py`](../../../app/core/inference_runner.py), and [`pyproject.toml`](../../../pyproject.toml).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: Host hardware telemetry queried via `psutil` and `torch`: CPU utilization percentage, physical memory utilization (used of total GB), compute device (NVIDIA GPU model via CUDA or fallback Host CPU), and storage headroom on the evidence partition.
- `code-present (runtime unverified)`: Pipeline subsystem status inspection:
  - YOLO26s-Pose Detector: verifies `models/yolo26s-pose.pt` checkpoint presence and loadability.
  - Temporal Fall Classifier: verifies `models/v6_3_phase3b/` frozen weight directory.
  - Local Incident Database: verifies local SQLite database file accessibility (`eldercare_demo.db`).
  - Advisory VLM Engine: checks if local or remote VLM provider is enabled and displays provider model label.
- `code-present (runtime unverified)`: Subsystem table with badge color indicators, functional descriptions, and exact local artifact filesystem paths.
- `code-present (runtime unverified)`: Architecture deployment card clarifying standalone demo operation versus production MQTT/WebSocket topologies.
- `partial`: Hardware metrics are synchronous point-in-time samples captured upon page render; there is no streaming time-series history or historical sparkline within this view.
- `partial`: Subsystem verification tests file presence and class instantiability, but does not benchmark inference throughput (FPS) or memory bandwidth on the telemetry page itself.
- `absent`: Remote server cluster health, network bandwidth monitors, automated hardware alerts, and historical error logs.

## 3. Proposed hierarchy

1. View Header: Title `System Telemetry`, local edge telemetry eyebrow, Host Operational badge, and diagnostic overview.
2. Host Hardware Allocation: Four solid cards for CPU Utilization, Physical RAM, Compute Device (GPU/CPU), and Storage Headroom.
3. Inference & Pipeline Subsystems: Structured panel listing each critical pipeline component (YOLO Pose, Temporal Classifier, SQLite Ledger, Advisory VLM) with active/inactive status pill, purpose, and filesystem path in IBM Plex Mono.
4. Architecture & Deployment Boundary: Explanatory card delineating local standalone demo boundaries from distributed production deployments (MQTT/WebSockets).
5. Quick Refresh Action: Manual refresh button to poll immediate host metrics.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  Streamlit Shell [Sidebar: Brand · Status · Local privacy]
┌──────────────────────────────────────────────────────────────────────────────┐
│ System Telemetry         LOCAL EDGE TELEMETRY · HEALTH MONITOR               │
│ Real-time diagnostic metrics from the local edge machine.    [Host Operational]│
├──────────────────────────────────────────────────────────────────────────────┤
│ HOST HARDWARE ALLOCATION                                                     │
│ ┌───────────────┬────────────────┬────────────────┬────────────────────────┐ │
│ │ CPU Load      │ Physical RAM   │ Compute Device │ Storage Headroom       │ │
│ │ 24%           │ 48% (7.6/16GB) │ NVIDIA RTX 3070│ 184 GB Free            │ │
│ │ Available     │ Normal Range   │ CUDA Enabled   │ Evidence Partition     │ │
│ └───────────────┴────────────────┴────────────────┴────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ INFERENCE & PIPELINE SUBSYSTEMS                                              │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ [● Active] YOLO26s-Pose Detector     | 17 Keypoints | `models/yolo26s...`│ │
│ │ [● Active] Temporal Fall Classifier  | V6.3 Frozen  | `models/v6_3...`   │ │
│ │ [● Active] Local Incident Database   | SQLite Store | `demo/eldercare.db`│ │
│ │ [○ Inactive] Advisory VLM Engine     | Scene Reason | `Disabled (Local)` │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ ARCHITECTURE & BOUNDARIES                                                    │
│ Standalone local demo operation; no continuous external telemetry egress.   │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844  Streamlit Mobile
[Menu] System Telemetry
[CPU Load: 24%] [RAM: 48%]
[Compute: RTX 3070] [Storage: 184GB]
[Subsystems List Stacked]
[Architecture Note Card]
```

## 5. Controls and states

- Controls: Page reload/refresh, code snippet copying for artifact paths, sidebar navigation.
- Normal Operation: All four hardware cards render valid numeric readings; detector and classifier show green `Active` badges.
- Elevated Resource State: CPU >80% or RAM >85% transitions delta badge to amber `Elevated Load` to warn the operator of potential frame pacing degradation.
- GPU Unavailable: If CUDA is not detected, Compute Device card displays `Host CPU` with an amber `CUDA Not Detected` notice and notes CPU-bound inference.
- Model Missing State: If model weights are missing, the corresponding subsystem badge displays gray `Inactive` with an inline alert pointing to model setup scripts.
- VLM State: Correctly displays whether optional multimodal scene reasoning is active or unconfigured, without treating disabled VLM as a system failure.

## 6. Responsive and accessibility rules

- At 390px, stack hardware cards into a 2x2 grid or single column; format subsystem rows as stacked cards with path text wrapped cleanly.
- Ensure all status badges include descriptive text (`Active`, `Inactive`, `Elevated Load`) rather than relying on color alone.
- Monospace font (`IBM Plex Mono`) is used for filesystem paths, hardware model strings, and memory values to ensure legible character alignment.
- Maintain high contrast on all card surfaces against the canvas background.

## 7. Synthetic image prompt

```text
Design a synthetic Streamlit system telemetry dashboard reference for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white cards with crisp borders, no translucent glass blur or floating 3D graphics. Top area displays “System Telemetry” with a green “Host Operational” pill. Four solid hardware cards show CPU Utilization (24%), Physical Memory (48% - 7.6 of 16.0 GB), Compute Device (NVIDIA RTX 3070 / CUDA Enabled), and Storage Headroom (184 GB). The middle section features a structured subsystem verification card with clean rows for YOLO26s-Pose Detector (Active green badge, path models/yolo26s-pose.pt), Temporal Fall Classifier (Active green badge, models/v6_3_phase3b/), Local Incident Database (Active), and Advisory VLM Engine (Inactive gray badge). Bottom card summarizes standalone architecture boundaries. Desktop 1440x1000; mobile 390x844 stacks elements. Synthetic telemetry graphics only, no code.
```
