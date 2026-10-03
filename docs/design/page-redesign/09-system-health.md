# 09 — System health page (`/app/telemetry`)

## 1. Purpose and source paths

- Purpose: show current host telemetry, service state, camera freshness, software/model metadata, and the distinction between API readiness and an actively usable detector.
- Current sources: [`frontend/src/pages/TelemetryPage.tsx`](../../../frontend/src/pages/TelemetryPage.tsx), [`frontend/src/components/charts/Charts.tsx`](../../../frontend/src/components/charts/Charts.tsx), [`frontend/src/hooks/DashboardContext.tsx`](../../../frontend/src/hooks/DashboardContext.tsx), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), [`src/eldercare/api/routers/health.py`](../../../src/eldercare/api/routers/health.py), [`src/eldercare/api/routers/system.py`](../../../src/eldercare/api/routers/system.py), and [`src/eldercare/api/routers/live.py`](../../../src/eldercare/api/routers/live.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: polls `/system/metrics` every two seconds, renders current/history CPU, memory, GPU, FPS, latency, service readiness, camera status, model/version/config, and manual refresh.
- `code-present (runtime unverified)`: backend exposes `/ready`, `/system/status`, and live metrics; camera rows link to Settings.
- `partial`: `/ready` maps live-manager existence to `vision_service`; that is not model-weight readiness. `detector_ready`, source phase, last-frame freshness, and API/database state need separate labels.
- `partial`: integrations are hardcoded `mqtt`/`vlm` disabled in the system status response; do not present them as dynamically tested provider health.
- `demo/mock`: fixture/API test telemetry can render sample values; no live host/GPU check was performed for this documentation task.
- `absent`: persistent telemetry history, export, log viewer, and incident-level trace are not present.

## 3. Proposed hierarchy

1. Header: System health, `Refresh status`, last sample time, and connection state.
2. Current host card: FPS/latency, CPU, memory, GPU with `No NVIDIA GPU` or unavailable label.
3. Readiness matrix: API, database, live manager, detector weights, active source, stream freshness, WebSocket, MQTT/VLM optional state.
4. Camera list: name, status, last heartbeat/frame, reconnect count, and link to camera settings.
5. Software card: model/config/API versions and source of each value.
6. Limitations: session-local history and current-host scope.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ System health                             [Refresh status] [last sample]      │
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Current host: FPS · avg/p95 latency · CPU · memory · GPU                 │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌───────────────────────────────┐ ┌────────────────────────────────────────┐ │
│ │ Readiness matrix              │ │ Cameras                                │ │
│ │ API / DB / manager / detector │ │ name · stream · frame age · reconnects│ │
│ │ source / freshness / optional │ │                                        │ │
│ └───────────────────────────────┘ └────────────────────────────────────────┘ │
│ Software versions + session-local history qualification                        │

390 × 844
[menu] System health [Refresh]
[last sample + connection]
[host metrics stacked]
[readiness rows]
[cameras]
[software]
```

## 5. Controls and states

- Controls: Refresh status, camera Manage link, optional expanders for metric definitions.
- Loading: show `Measuring…`, `Checking services…`, and `Loading cameras…` per resource; retain last sample only with a stale timestamp.
- Error: distinguish telemetry polling, readiness, system metadata, and camera list errors; each has Retry and does not turn into zero.
- Empty: no cameras says they appear after the first source starts; no history says `Collecting samples`.
- Stale: display sample age and stop using green/ready language after a defined freshness window; state the window in implementation documentation.
- Readiness: separate `API reachable`, `database ready`, `live manager present`, `detector weights loaded`, `active source`, `last frame`, and optional integrations. Unknown is visible as Unknown.
- Hardware: use `No NVIDIA GPU` only when the measured response says so; do not infer a GPU from benchmark artifacts.

## 6. Responsive and accessibility rules

- At 390px, stack metric tiles and readiness rows; keep the Refresh action beside the title and make age/units visible in each row.
- Charts include labelled values/table fallback and never rely on colour; meters expose `aria-valuenow`, `aria-valuemin`, and `aria-valuemax` when numeric.
- Use semantic sections, `aria-live` for refresh status, and monospace for model/config/version/units.
- Announce stale/error changes politely; do not repeatedly announce every two-second sample.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated System health page for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no 3D art or decorative reliability percentages. Show desktop 232px sidebar + 72px top bar, Refresh status, sample age, measured host FPS/latency/CPU/memory/GPU tiles, a readiness matrix separating API/database/live manager/detector weights/source/frame freshness, camera health rows, and model/config/API metadata. Adapt to mobile 390x844 with stacked rows and visible units. Use synthetic values labelled illustrative or “Not measured”; no real host claims, patient data, emergency guarantees, or code.
```
