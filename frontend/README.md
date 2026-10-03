# ElderCare Vision frontend

React 19, Vite, TypeScript and plain CSS. The dashboard talks to the ElderCare Vision API: operator accounts, live fall detection on a webcam or video file, incidents, reviews, settings and telemetry are all served by the backend.

## Run

Start the API (from the repository root), then the frontend:

```powershell
uv run uvicorn eldercare.api.server:create_server_app --factory --port 8000
```

```powershell
npm install
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173 and create an account at `/signup` (the first account becomes the workspace admin). Vite proxies `/api` (REST, MJPEG and the event WebSocket) to `http://127.0.0.1:8000`; set `ELDERCARE_API_URL` to proxy elsewhere, or `VITE_API_BASE_URL` to call another origin directly.

Public routes are `/`, `/signin` and `/signup`. Dashboard routes (`/app`, `/app/surveillance`, `/app/incidents`, `/app/benchmarks`, `/app/telemetry`, `/app/review`, `/app/settings`) require a session.

## What runs where

- **Live monitor** (`/app/surveillance`): choose a camera the server detects, a labelled URFD dataset clip (the result is checked against its label), or your own uploaded video, then press Start. No camera setup is needed first: webcams are filed as `webcam-N`, videos under one "Video analysis" camera. The server runs YOLO26s-pose + the frozen V6.3 classifier at 15 Hz, streams annotated frames with a fall-likelihood trace, and saves each confirmed fall as an incident with three keyframes, alerting every open dashboard.
- **Overview / System health**: what needs review, falls today, what is running and the 7-day trend; detector speed, CPU/memory/GPU, services and cameras measured live.
- **Settings**: tabs for detection sensitivity and overlay, alerts, cameras (rename/disable), data retention and export, and your account and team.
- **Incidents / Review queue**: search and filter by decision (needs review, real falls, false alarms); review each incident from its keyframes, or work through every unreviewed one with the F / N / U / S keys. Decisions are append-only and attributed to the signed-in operator.

Not provided: password reset by email, Google sign-in, SMS/phone escalation. `VITE_USE_MOCK=true` switches to the fixture transport used by the component tests.

Research/portfolio prototype, not a certified medical device or guaranteed emergency service.

## Design and evidence

User-supplied mockups are preserved in `website idea/`. Generated images and their briefs are listed in `src/assets/ASSETS.md`; the local font license is preserved alongside them. Charts are inline SVG.

Benchmark values are a small approved snapshot of `docs/reports/V6_FINAL_RESULTS.md` and its saved JSON artifact: 98.3% recall, 96.7% precision, 0.85 s median and 1.58 s p95 alert time. They are evaluation results, not live application guarantees. The false-alarm target stays “Under evaluation.” The PR chart shows one measured operating point; unmeasured curves and previous-version comparisons are not fabricated.

Research/portfolio prototype, not a certified medical device or guaranteed emergency service.

## Verify

```powershell
npm run typecheck
npm run lint
npm run test
npm run build
```

Visual/browser evidence is saved under `output/playwright/`. Static hosting needs an index.html fallback for SPA deep links and a reverse proxy for `/api` to the API server.
