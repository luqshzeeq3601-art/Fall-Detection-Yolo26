# 04 — Overview page (`/app`)

## 1. Purpose and source paths

- Purpose: answer “what needs attention now?” with review backlog, recorded incidents, active sources, and service readiness, then route to Live monitor or review work.
- Current sources: [`frontend/src/pages/DashboardPage.tsx`](../../../frontend/src/pages/DashboardPage.tsx), [`frontend/src/pages/DashboardPage.css`](../../../frontend/src/pages/DashboardPage.css), [`frontend/src/hooks/DashboardContext.tsx`](../../../frontend/src/hooks/DashboardContext.tsx), [`frontend/src/hooks/useIncidents.ts`](../../../frontend/src/hooks/useIncidents.ts), [`frontend/src/features/live/useLiveStatus.ts`](../../../frontend/src/features/live/useLiveStatus.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), [`src/eldercare/api/routers/incidents.py`](../../../src/eldercare/api/routers/incidents.py), and [`src/eldercare/api/routers/health.py`](../../../src/eldercare/api/routers/health.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: incident statistics, latest incidents, active live sessions, readiness, camera names, start-monitoring links, and last-seven-day incident counts.
- `code-present (runtime unverified)`: dashboard refreshes recent incidents/stats on selected WebSocket events and renders loading, retry, and empty states for those requests.
- `demo/mock`: deterministic incident/camera/readiness fixture data is available through `MockApiClient`; the `VITE_USE_MOCK` path is not a production telemetry proof.
- `partial`: `useLiveStatus` records polling errors, but Overview currently does not make a live-status error or stale stream timestamp prominent; “Monitoring” can remain `Idle` or last-known without a clear freshness explanation.
- `partial`: `/ready` reports database and live-manager readiness; it does not prove model weights are loaded or that a source is streaming. Keep `ready`, `detector_ready`, and stream freshness separate.
- `absent`: no operational reliability percentage, emergency escalation, or caregiver staffing view.

## 3. Proposed hierarchy

1. Header: Overview, one-line purpose, Start monitoring.
2. Attention strip: Needs review first, then active source state, today’s incidents, and backend readiness with timestamps.
3. Main split: large current source panel on the left; latest incidents list on the right.
4. Activity section: measured seven-day count series as a compact accessible table plus optional chart, never a decorative trend claim.
5. Evidence note: a quiet boundary card for source freshness, API/demo mode, and research-POC status.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar: search · connection · alerts · operator]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Overview                                      [Start monitoring]              │
│ [Needs review] [Monitoring + freshness] [Falls today] [Backend readiness]     │
│ ┌──────────────────────────────┐ ┌─────────────────────────────────────────┐ │
│ │ Current source / empty start │ │ Latest incidents                        │ │
│ │ stream state + detector      │ │ time · camera · score · review          │ │
│ └──────────────────────────────┘ └─────────────────────────────────────────┘ │
│ Activity last 7 local days [accessible table / measured chart]                │
│ source freshness · demo/runtime qualification                                  │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844
[menu] Overview [Start monitoring]
[Needs review]
[Monitoring + freshness]
[Falls today] [Backend readiness]
[Current source / start choices]
[Latest incidents]
[Activity table]
```

## 5. Controls and states

- Controls: Start monitoring, source choices (camera/dataset/upload), links to Review queue/Incidents/System health, recent-incident selection, top-bar search, notification inbox.
- Loading: each panel owns its loading state; do not block the whole overview when only stats or cameras are slow.
- Empty: “Nothing is being monitored” with the three real source choices; “No falls recorded yet” links to Live monitor.
- Error: show the failing resource (`Incident totals unavailable`, `Camera status unavailable`, `Readiness unavailable`) with Retry and System health path.
- Stale/live error (proposed repair): show last successful poll time and a red/amber banner when `/live/status` fails; do not display a fresh-looking green state from old data.
- Readiness: display backend reachable, database state, live-manager state, and detector/source freshness as distinct rows; never call the whole system healthy from one `/ready` response.

## 6. Responsive and accessibility rules

- At 390px, stack KPI cards and source/incidents panels; move Start monitoring immediately below the title.
- Use `main`, labelled sections, one `h1`, list semantics for incidents, and a text equivalent for the seven-day series.
- Announce changing alert counts politely; do not steal focus when WebSocket events refresh a panel.
- Preserve tab order through the source start choices and incident links; status labels include text and timestamps.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Overview page for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels; no glass blur or 3D art in operations. Show a 232px desktop sidebar, 72px top bar, max 1280px content, attention cards for Needs review, Monitoring with freshness, Falls today, and backend readiness, a current-source panel with clear idle state, latest incidents, and a measured seven-day table/chart. Explicitly label synthetic/demo data and runtime qualification. Desktop 1440x1000; mobile 390x844 stacks panels and keeps Start monitoring visible. No real patient footage, fabricated health percentages, medical guarantees, or code.
```
