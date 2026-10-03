# 05 — Live monitor page (`/app/surveillance`)

## 1. Purpose and source paths

- Purpose: choose a source, start/stop the local inference session, inspect annotated output and state, and follow saved detections to incident review.
- Current sources: [`frontend/src/pages/SurveillancePage.tsx`](../../../frontend/src/pages/SurveillancePage.tsx), [`frontend/src/features/live/LiveMonitor.tsx`](../../../frontend/src/features/live/LiveMonitor.tsx), [`frontend/src/features/live/SourcePicker.tsx`](../../../frontend/src/features/live/SourcePicker.tsx), [`frontend/src/features/live/StreamViewer.tsx`](../../../frontend/src/features/live/StreamViewer.tsx), [`frontend/src/features/live/LikelihoodTrace.tsx`](../../../frontend/src/features/live/LikelihoodTrace.tsx), [`frontend/src/features/live/useLiveStatus.ts`](../../../frontend/src/features/live/useLiveStatus.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), [`src/eldercare/api/routers/live.py`](../../../src/eldercare/api/routers/live.py), and [`src/eldercare/live/engine.py`](../../../src/eldercare/live/engine.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: tabs for detected camera, labelled dataset clip, and uploaded video; camera scan; dataset filter/search; upload progress/cancel/delete; optional file loop; Start/Stop.
- `code-present (runtime unverified)`: live MJPEG viewer, annotated state, snapshot download, ten-second WebM recording, fullscreen, fall-likelihood trace, detector-state ladder, run summary, dataset-label verdict, and incident links.
- `code-present (runtime unverified)`: API live endpoints start a source, poll `/live/status`, serve stream/snapshot, and expose current/history metrics; `src/eldercare/live/engine.py` is shared with the Streamlit wrapper.
- `demo/mock`: tests and fixture transports provide synthetic sessions and sample files; a `VITE_USE_MOCK` screen is not camera/GPU proof.
- `partial`: polling errors are stored by `useLiveStatus` but are not always prominent; `ready`/manager reachability, `detector_ready`, source phase, and last-frame freshness must be separate visible states.
- `absent`: RTSP credential/configuration UI, cloud video, emergency dispatch, and continuous provider upload are not supported.

## 3. Proposed hierarchy

1. Header: Live monitor, source count, explicit backend/stream freshness badge.
2. Main viewer: source label, stream or empty frame, state badge, Stop/Snapshot/Record controls, and run summary.
3. Evidence trace: measured likelihood/time series with threshold label and text table fallback.
4. Source rail: Camera, Dataset clip, Your video tabs with selection, scan/upload states, and one Start action.
5. Detector state rail: `No person → Upright → Possible fall → Fall confirmed`, plus detector-ready and last-frame metadata.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Live monitor                         [Idle / 1 source running] [freshness]    │
│ ┌──────────────────────────────────────────┐ ┌──────────────────────────────┐ │
│ │ Viewer: source label       LIVE/ANALYSING│ │ Video source                  │ │
│ │ [annotated frame or empty state]         │ │ [Camera][Dataset][Your video]│ │
│ │ [Stop] [Snapshot] [Record 10 s] [full]   │ │ source list / upload          │ │
│ │ run summary + detections                 │ │ [Start ...]                   │ │
│ └──────────────────────────────────────────┘ │ Detector state ladder         │ │
│ [likelihood trace + table + threshold]       │ │ ready/freshness               │ │
└──────────────────────────────────────────────┴──────────────────────────────┘

390 × 844
[menu] Live monitor [Idle/freshness]
[Viewer + state + Start/Stop]
[Run summary / detections]
[likelihood table]
[source tabs + list/upload]
[detector state]
```

## 5. Controls and states

- Controls: source tabs, camera scan, radio selection, clip filters/search, upload/dropzone/cancel/delete, loop checkbox, Start, Stop, Snapshot, Record 10 s, fullscreen, running-source tabs.
- Loading: camera scan says `Looking for cameras…`; source files and upload show progress; Start changes to a busy state; viewer says `Loading the detector…` when the session is starting.
- Empty: no camera found includes a repair path and offers dataset/upload; no uploads says `Nothing uploaded yet`; no detections says `None so far`.
- Error: distinguish source scan/upload/start/stream/frame/persistence errors and provide Retry, choose another source, or review saved detections. Do not silently continue after a failed stream.
- Stale (proposed repair): show last `/live/status` success and last frame time; amber when polling is stale, red when stream image failed, while retaining the last frame with a stale label.
- Detector readiness: `backend reachable`, `detector loading`, `detector ready`, and `pass-through/no weights` are separate; a live manager is not evidence that model weights loaded.
- Dataset finished: show `Matches the label` or `Does not match the label` only for clips with a known expected label; uploaded videos have no ground-truth verdict.

## 6. Responsive and accessibility rules

- At 390px, put viewer and primary start/stop action first; source and detector rails follow as stacked panels.
- Source tabs use an ARIA tablist with arrow-key navigation; source options use labelled radios; progress bars expose numeric values.
- Viewer controls have text labels or accessible names; stream alt text names the source; live status is polite and does not steal focus.
- Keep trace values available in a table/list, avoid colour-only likelihood states, and respect reduced motion for live indicators.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Live monitor page for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no 3D art or decorative glass in operations. Show a large synthetic annotated video placeholder with clear LIVE/ANALYSING state, Stop/Snapshot/Record controls, a measured likelihood trace with table fallback, Camera/Dataset clip/Your video tabs, source selection/upload states, and a detector ladder from No person to Fall confirmed. Show distinct backend, detector-ready, source phase, and frame-freshness labels. Desktop 1440x1000 uses 232px sidebar + 72px top bar; mobile 390x844 stacks viewer then source controls. No real people, real footage, credentials, fabricated health claims, emergency guarantees, or code.
```
