# ElderCare Vision page redesign briefs

## 1. Purpose

- These are design proposals for the current React routes and the five current Streamlit views.
- They document source-backed behavior, missing or qualified capabilities, and a concrete responsive redesign direction.
- They do not implement UI, generate images, change backend/model/data files, or prove browser, camera, GPU, or production behavior.
- Read the shared rules first: [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md).
- The companion source audit is [CURRENT_FUNCTIONALITY_AUDIT.md](./CURRENT_FUNCTIONALITY_AUDIT.md).

## 2. Source and evidence boundary

- React routing is in [`frontend/src/App.tsx`](../../../frontend/src/App.tsx); authenticated shell/navigation is in [`frontend/src/components/layout/Shell.tsx`](../../../frontend/src/components/layout/Shell.tsx).
- The HTTP boundary is [`frontend/src/api/client.ts`](../../../frontend/src/api/client.ts) and [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts); deterministic fixtures are [`frontend/src/api/mockClient.ts`](../../../frontend/src/api/mockClient.ts) and [`frontend/src/api/mockData.ts`](../../../frontend/src/api/mockData.ts).
- Current backend boundaries are under [`src/eldercare/api/routers/`](../../../src/eldercare/api/routers/); the shared live engine is [`src/eldercare/live/engine.py`](../../../src/eldercare/live/engine.py).
- Streamlit navigation and view registration are in [`streamlit_app.py`](../../../streamlit_app.py) and [`app/core/nav.py`](../../../app/core/nav.py).
- Historical screenshots and old mock descriptions are reference material only. The current source and named artifacts control these briefs.

## 3. Brief index

### React routes

1. [Landing](./01-landing.md) — `/`
2. [Sign in](./02-sign-in.md) — `/signin`
3. [Sign up](./03-sign-up.md) — `/signup`
4. [Overview](./04-overview.md) — `/app`
5. [Live monitor](./05-live-monitor.md) — `/app/surveillance`
6. [Incidents](./06-incidents.md) — `/app/incidents`
7. [Review queue](./07-review-queue.md) — `/app/review`
8. [Benchmarks](./08-benchmarks.md) — `/app/benchmarks`
9. [System health](./09-system-health.md) — `/app/telemetry`
10. [Settings](./10-settings.md) — `/app/settings`
11. [Not found](./11-not-found.md) — unmatched paths
12. [Incident detail panel](./12-incident-detail.md) — companion to Incidents and Review queue

### Streamlit companion views

13. [Streamlit overview](./13-streamlit-overview.md) — `overview`
14. [Streamlit live demo](./14-streamlit-live-demo.md) — `live-demo`
15. [Streamlit incidents review](./15-streamlit-incidents-review.md) — `incidents`
16. [Streamlit benchmarks gate](./16-streamlit-benchmarks-gate.md) — `results`
17. [Streamlit system telemetry](./17-streamlit-system-telemetry.md) — `system`

## 4. Review checklist

- Every brief names current source paths and marks claims `code-present (runtime unverified)`, `demo/mock`, `partial`, `absent`, or `proposed`.
- Every brief has a hierarchy, an ASCII wireframe, controls and loading/error/empty states, desktop/mobile adaptation, accessibility rules, and a self-contained synthetic image prompt.
- Operations preserve the evidence contact strip and make missing/stale data explicit.
- Benchmark redesign removes unsupported trends, decorative curves, fabricated runtime tiles, and deployment-gate language that the artifacts cannot support.
