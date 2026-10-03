# Current functionality audit

## 1. Scope and evidence

- Inspected on **2026-10-02**, against the current working tree, including uncommitted code.
- This is a functionality and design audit, not a deployment certification. **Code-present** means an implementation and its wiring were inspected; it does not mean the camera, GPU, browser permissions or provider were tested live.
- **Demo/mock** means fixture, illustration or hardcoded presentation. **Partial** means a control exists with incomplete wiring or misleading presentation. **Absent** means no implementation was located within the inspected frontend/API/demo paths. **Proposed** means a redesign or future repair.
- Scope: ten React routes, the catch-all page, incident detail panel, and five separate Streamlit views. The companion views are not new React routes.
- Source of navigation: [React routes](../../../frontend/src/App.tsx) and [Streamlit entrypoint](../../../streamlit_app.py).
- Older architecture and Phase 6 reports describe mock-only auth/settings/live features. The current working tree has newer API code. Treat those reports as historical rather than proof of present behavior.

## 2. Current React page inventory

| Page / route | Code-present functionality | Partial, missing or mock boundary | Redesign brief |
|---|---|---|---|
| Landing `/` | Sign-in/account/dashboard links, anchored workflow/results/privacy sections, static evaluation snapshot | Unqualified speed/privacy claims; evaluation snapshot is not live performance | [Landing](01-landing.md) |
| Sign in `/signin` | Email/password validation, visibility toggle, remember option, login/session redirect | Email reset explains unavailability; no reset delivery or social login | [Sign in](02-sign-in.md) |
| Sign up `/signup` | Account and care-context inputs, validation, terms acknowledgement, API account creation | No invitation, email verification or social signup workflow located | [Sign up](03-sign-up.md) |
| Overview `/app` | Incident aggregates, recent incidents, source-start links, first active stream, seven-day counts, readiness | Confirmed detector incidents are titled “Falls”; poll failures/unknown values need clearer handling | [Overview](04-overview.md) |
| Live monitor `/app/surveillance` | Host webcam scan, URFD sample selection, upload/progress/cancel/delete, start/stop, MJPEG, snapshot, browser recording, fullscreen, likelihood trace, run summary | No RTSP selector in current source contract; source streaming does not prove detector ready; recording depends on browser support | [Live monitor](05-live-monitor.md) |
| Incidents `/app/incidents` | Search, camera/date/review filters, pagination, selected incident, evidence, review history | No resident identity directory; no arbitrary video seek or server incident clip identified | [Incidents](06-incidents.md) |
| Review queue `/app/review` | Unreviewed queue, selectable saved keyframes, real-fall/false-alarm/unsure writes, local skip, R/F/U/S shortcuts, 500-character note, session progress | Skip is visit-local and clears its note; does not save a review; no automatic retraining or incident-video playback | [Review queue](07-review-queue.md) |
| Benchmarks `/app/benchmarks` | Static V6.3 snapshot, source report link, activity results, detected-event alert times | Several unsupported chart values and a dead dataset control; see section 4 | [Benchmarks](08-benchmarks.md) |
| System health `/app/telemetry` | Two-second metrics polling, session-local history, service/camera/version display, refresh | Readiness is incomplete; no persistent history query, telemetry export or log viewer located | [System health](09-system-health.md) |
| Settings `/app/settings` | Server settings, calibration overrides, overlays/head blur, notifications/sound, camera rename/enable, retention/export, password change/team listing | No RTSP add/test form, provider configuration panel, team invite or role editor; saved options need scope/effective-time explanation | [Settings](10-settings.md) |
| Catch-all `*` | Page-not-found message and return-home link | No route-specific recovery or authenticated-shell explanation | [Not found](11-not-found.md) |
| Incident detail, embedded | Three keyframe references, review controls/history, detector facts, optional generated context | Not a standalone route; missing keyframes and failed image loads need explicit states | [Incident detail](12-incident-detail.md) |

Sources: [pages](../../../frontend/src/pages/), [platform API calls](../../../frontend/src/api/platform.ts), [live controls](../../../frontend/src/features/live/LiveMonitor.tsx), [source picker](../../../frontend/src/features/live/SourcePicker.tsx), [incident detail](../../../frontend/src/components/incidents/IncidentDetail.tsx).

## 3. Implemented backend versus unsupported operations

1. **Accounts and sessions are code-present.**
   - [Auth routes](../../../src/eldercare/api/routers/auth.py) provide signup, login, logout, current user, password change and admin team listing.
   - [Server factory](../../../src/eldercare/api/server.py) enables session checks by default and can use local SQLite or configured PostgreSQL.
   - This does not establish email verification, reset-by-email, administrator reset, invitations, role management or SSO.

2. **Live source analysis is code-present.**
   - [Live API](../../../src/eldercare/api/routers/live.py) supports source catalog, uploads, webcam discovery, source test/start/stop, frame stream, snapshot and metrics.
   - [Source contract](../../../frontend/src/api/platform.ts) exposes `webcam` and `file`. Separate RTSP ingest components elsewhere in the repository do not make RTSP setup available in this interface.
   - [Live session](../../../src/eldercare/live/session.py) can stream even when model weights are unavailable; `detector_ready` and the error message must remain visible.
   - The current [Streamlit wrapper](../../../app/core/inference_runner.py) imports the same [frozen V6.3 engine](../../../src/eldercare/live/engine.py) as the API worker. Earlier notes about a separate heuristic engine are superseded in source. Live accuracy/throughput remains unverified here.

3. **Persistence, reviews and retention are code-present.**
   - [Incident routes](../../../src/eldercare/api/routers/incidents.py) expose list/detail/evidence/reviews/statistics/export. Reviews are append-only; detector output stays separate.
   - [Workspace settings](../../../src/eldercare/api/workspace.py), [settings routes](../../../src/eldercare/api/routers/settings.py) and [retention policy](../../../src/eldercare/incidents/retention.py) are implementations, not merely visual toggles.
   - [App lifespan](../../../src/eldercare/api/app.py) runs the retention check hourly for the runnable live server. A design must warn before destructive retention changes and never illustrate a save as success before the response.

4. **Optional enrichment exists, but its readiness and presentation need qualification.**
   - [App enrichment lifespan](../../../src/eldercare/api/app.py) starts configured asynchronous workers. [Incident detail](../../../frontend/src/components/incidents/IncidentDetail.tsx) displays provider/model context separately from detector evidence.
   - There is no current Settings UI for selecting the provider, editing its endpoint or entering a key.
   - [Provider factory](../../../src/eldercare/agents/factory.py) supports HTTP/OpenAI-compatible providers; [provider client](../../../src/eldercare/agents/client.py) can send incident image bytes. “All frames never leave the machine” is too broad when optional remote enrichment is configured.
   - No generated text should identify injury, assign medical severity, overwrite raw evidence or imply automatic emergency escalation.

5. **Notifications are browser/dashboard actions.**
   - Browser permission, sound and WebSocket/dashboard notices are code-present. They require an open supported client and available connection.
   - SMS, phone calls, emergency dispatch and guaranteed delivery are absent in the inspected application paths.

## 4. Mock presentation and misleading controls to correct

| Finding | Current source evidence | Proposed correction |
|---|---|---|
| Unsupported version trends | `BenchmarksPage.tsx:74–98`: `+0.8%`, `+1.1%`, `-0.32 s` versus V6.2 | Remove until matched evaluation artifacts establish each comparison |
| Decorative KPI sparklines shown as measurement | `BenchmarkCharts.tsx:50–104`: literal SVG paths | Remove; a snapshot has no time series |
| Wrong no-fall confusion cells | `BenchmarkCharts.tsx:154–160`: FP 3.3%, TN 96.7% | Clip-level table: fall detected 59, missed 1; ADL alerted 1, quiet 71. Keep event precision separate |
| Invented PR curve | `BenchmarkCharts.tsx:224–266`: literal path/points | One sourced operating point, labelled “Threshold sweep unavailable” |
| Unsupported prior-version comparison | `BenchmarkCharts.tsx:307–337`: V6.2 97.5%/95.6%/1.90 s and FA/h 0.8 | Separate sourced development history from final evaluation; no matched sealed-version claim |
| Unsupported runtime/false-alarm tiles | `BenchmarkCharts.tsx:388–418`: 0.6/h, 32 ms, 28 FPS, GPU 62%, CPU/RAM 28%/5.1 GB | Use an identified measured artifact or “Not measured”; put current hardware readings on System health |
| Future evaluation date | `BenchmarkCharts.tsx:443`: Oct 1–Oct 7, 2026 | Use the artifact timestamp; do not imply a future measured run |
| Dataset selector has no behavior | `BenchmarksPage.tsx:55`: focusable `div` without handler | Static provenance chip for the single available snapshot; selector only after datasets are wired |
| Readiness does not prove detection | `health.py:50–51`: manager existence → ready; `system.py` static integration labels | Separate API/database, source, model readiness and last-frame age; expose unknown/error |
| Streamlit engine badge is static | `streamlit_app.py:94`: “Engine Online”, “v6.3 Sealed” | Derive from loaded models/active run; “sealed evaluation” belongs to the benchmark artifact |
| Streamlit sample-count text conflicts with artifact | `app/views/benchmarks.py:201`: “31 fall sequences” | Use artifact counts: 60 fall camera clips and 72 ADL camera clips; explain the counting unit |
| Team-list failures are hidden | `SettingsPage.tsx:95–103`: failed `authApi.team()` request is ignored | Show admin-only, loading, unavailable and retry states separately |
| Landing copy implies review is guaranteed | `LandingPage.tsx:31–34`: “Every alert is confirmed by designated personnel” | Explain that alerts await human review; do not promise every alert has been reviewed |

These findings describe the present code. This documentation task does not repair the application implementation.

## 5. Metric and evidence rules

- The [final JSON](../../reports/V6_3_FINAL_TESTB_EVALUATION.json) and [results report](../../reports/V6_FINAL_RESULTS.md) support 59/60 detected fall events, two false alert events, event precision about 96.7%, and p95 onset-to-alert of 1.579 s.
- A **clip-level** confusion table has 59 detected fall clips, 1 missed fall clip, 1 ADL clip with an alert, and 71 ADL clips without alerts. Its alerting-clip precision differs from event-level precision because one extra alert occurred inside a fall clip. Label both units.
- Test-B contains different recordings of people seen during development diagnostics. Do not claim unseen-person generalisation.
- Longform held-out exposure is about 0.83 h, with zero observed alerts and a 95% upper bound about 3.59/h. The raw JSON marks the point-estimate gate passed; that is insufficient to establish the 0.05/h rate with useful uncertainty. Show “False-alarm target unproven”.
- Saved evaluation results do not establish the current host's live camera-to-alert latency, GPU runtime or household accuracy.
- No V6.3 AUC or threshold-sweep curve was found. Older V4 development AUC values are not valid substitutes.
- [KeyframeStrip](../../../frontend/src/components/incidents/KeyframeStrip.tsx) currently orders “At the alert”, “1.5 s before”, “3 s before”. A proposed chronological strip must use “3 s before → 1.5 s before → At alert”; no post-alert frame is guaranteed. Offsets are requested samples, not proof of exact onset timing. Missing/short-history evidence must be disclosed.
- Image prompts use **synthetic illustration** labels, fictitious generic IDs and placeholder metrics. Generated screenshots are design concepts, never benchmark or live-run evidence.

## 6. Demo mode and visual mockup boundaries

- [API boundary](../../../frontend/src/api/index.ts) selects `MockApiClient` only for `VITE_USE_MOCK=true`. [Auth provider](../../../frontend/src/features/auth/AuthProvider.tsx) then starts with a fixture operator.
- [Platform calls](../../../frontend/src/api/platform.ts) still use direct HTTP for live status, metrics, settings, aggregates and account operations. Demo mode is therefore **not a fully isolated mock application**; tests intercept these requests where needed. A future design should label provenance by panel and surface unavailable responses rather than silently borrowing fixture success.
- Supplied [settings mockup](../../../frontend/website%20idea/settings.png) suggests RTSP editing/testing, provider configuration and extra navigation categories. These are reference artwork, not feature evidence. The new Settings brief follows the five existing sections and separates future capabilities.
- Existing [saved overview screenshot](../../../frontend/output/playwright/overview-1440.png) shows synthetic playback and fixture values from an older layout. It was visually inspected as a historical design reference; it does not match all current source behavior.
- The design reduces large glass ornaments on operational screens, gives evidence the main visual space, uses readable solid panels and keeps one light theme across both interfaces.
- “Record 10 s” is a manual browser-side annotated-video capture/download, not automatic continuous server recording. Uploaded videos are stored server-side until deleted; incident retention does not by itself prove upload cleanup. Privacy copy must distinguish these paths.

## 7. Separate Streamlit view inventory

| View / path | Code-present behavior | Boundary | Brief |
|---|---|---|---|
| Overview `/` on Streamlit host | Project explanation, links, benchmark summaries and limitations | Separate frontend; summary copy can overstate privacy/status | [Streamlit overview](13-streamlit-overview.md) |
| Live Demo `/live-demo` | Sample/upload/webcam source, start/stop, annotations, temporal processing, persisted incident evidence | Host-local demo state; no authenticated React session workflow | [Streamlit live demo](14-streamlit-live-demo.md) |
| Incidents & Review `/incidents` | Saved evidence, filters, review form/history, optional context, JSONL export | Reviewer identifier can be entered manually; no React queue shortcuts implied | [Streamlit review](15-streamlit-incidents-review.md) |
| Benchmarks & Gate `/results` | Local artifact loading, final/development summaries and gate display | Narrative count mismatch; inadequate longform exposure must remain explicit | [Streamlit benchmarks](16-streamlit-benchmarks-gate.md) |
| System Telemetry `/system` | Hardware/package/model/storage/demo status | Standalone demo telemetry is different from API metrics | [Streamlit telemetry](17-streamlit-system-telemetry.md) |

Sources: [views](../../../app/views/), [demo backend](../../../app/core/backend.py), [artifact loader](../../../app/core/data_loader.py).

## 8. Priorities for a later implementation task

1. Correct benchmark provenance, metric units, inactive controls and unsupported presentation values.
2. Make detector-disabled, lost stream, polling error, stale metrics and persistence failure visible.
3. Apply the shared light palette/type/layout and chronological evidence hierarchy to existing workflows.
4. Clarify uploaded-video retention, optional provider evidence sharing, browser recordings and calibration changes before promising privacy or runtime effects.
5. Treat RTSP UI setup, invitation/reset workflows and provider settings as separate feature proposals. Do not introduce them silently during a visual redesign.

## 9. Verification limits

- Current frontend verification: **16 test files / 82 tests passed**, typecheck passed, lint passed, production build passed. Component tests use fixtures/mocks; they do not prove live camera or GPU behavior.
- Targeted backend tests were attempted. The local `.venv` Python launcher failed with permission denied; the bundled interpreter could not read `.venv` pytest packages. Backend tests were **not rerun successfully**.
- No fresh browser/server/camera/provider session was started. Supplied and historical saved images were inspected; new design images were not generated.
- Graph metadata references the older `eldercare-vision/` tree and lacks the current page names. Its CLI failed; current source inspection is the basis of this audit.
- Use [the design system](DESIGN_SYSTEM.md) and [page index](README.md) for the proposed redesign. Functionality fixes require implementation and new verification.
