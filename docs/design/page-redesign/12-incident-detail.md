# 12 — Incident detail companion panel

## 1. Purpose and source paths

- Purpose: make one detector-confirmed incident understandable and reviewable without mixing raw detector facts, human decisions, and optional generated context.
- Current sources: [`frontend/src/components/incidents/IncidentDetail.tsx`](../../../frontend/src/components/incidents/IncidentDetail.tsx), [`frontend/src/components/incidents/KeyframeStrip.tsx`](../../../frontend/src/components/incidents/KeyframeStrip.tsx), [`frontend/src/components/incidents/DecisionBar.tsx`](../../../frontend/src/components/incidents/DecisionBar.tsx), [`frontend/src/components/incidents/ReviewTag.tsx`](../../../frontend/src/components/incidents/ReviewTag.tsx), [`frontend/src/hooks/useIncidentDetail.ts`](../../../frontend/src/hooks/useIncidentDetail.ts), [`frontend/src/api/types.ts`](../../../frontend/src/api/types.ts), and [`src/eldercare/api/routers/incidents.py`](../../../src/eldercare/api/routers/incidents.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: selected-incident fetch, camera/time/review label, saved evidence URLs, append-only decision bar with optional note, optional enrichment status/output, detector facts, and review history.
- `code-present (runtime unverified)`: evidence access is mapped through incident/evidence IDs by the API client; details are keyed to the selected incident to avoid stale content.
- `demo/mock`: deterministic incident evidence/enrichment fixtures; some fixture incidents intentionally have no evidence.
- `partial`: current keyframe captions are alert-first (`At the alert`, `1.5 s before`, `3 s before`) and some saved incidents have fewer frames; the redesign should reorder chronologically while retaining nominal offsets and explicit missing slots.
- `partial`: optional generated text can be pending/failed and must remain visually separate; it must never infer injury, medical severity, or overwrite the detector/human label.
- `absent`: post-alert frame, arbitrary video seek, resident identity, emergency action, and automatic retraining are not supported.

## 3. Proposed hierarchy

1. Detail header: camera, confirmed time, incident ID, current review tag.
2. Observed evidence strip: `3 s before → 1.5 s before → At the alert`, each with stored timestamp/ID; missing or failed media is explicit.
3. Human decision bar: current label, Real fall/False alarm/Unsure, optional note, save status.
4. Detector facts: track, score, evidence features/reason, onset/confirmation, model/config.
5. Optional second opinion: provider/model/status and generated text with a persistent “does not override evidence or decision” label.
6. Append-only decision history.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  inside Incidents or Review queue
┌──────────────────────────────────────────────────────────────────────────────┐
│ Incident · Hallway camera · 07:10:04 · [Needs review] · ID                  │
│ [3 s before]       [1.5 s before]        [At the alert]                      │
│ [saved/missing]    [saved/missing]       [saved/missing]                     │
│ [Real fall] [False alarm] [Unsure]  [optional note________________]           │
│ Detector facts                    │ Optional second opinion                  │
│ Decision history                  │ Generated text; never overrides decision │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844
Incident header + ID
[3 s before]
[1.5 s before]
[At the alert]
[decision controls + note]
[facts]
[second opinion]
[history]
```

## 5. Controls and states

- Controls: evidence open-full-size links, three decisions, optional note, Detector details disclosure, and history links if present.
- Loading: show `Loading incident…` and `Loading keyframes…`; if the selected ID changes, clear/replace old evidence before showing the new incident.
- Empty: no selected ID says `Select an incident`; no evidence says `No keyframes were saved for this incident`; no review says `No decision recorded yet`.
- Evidence error: identify the missing evidence ID/frame and retain other frames; never substitute a synthetic image in the operational panel.
- Enrichment: pending/failed/completed states show provider/model/error code when available; disabled/unconfigured is a normal optional state.
- Save error: keep note and current decision; success says exactly which label was saved and refreshes history.
- Stale: show the incident’s captured/created timestamps and a refresh action when a detail request is older than the list selection.

## 6. Responsive and accessibility rules

- At 390px, frames stack or use a labelled horizontal scroller with each timestamp visible; decisions remain full-width and precede long facts.
- Use an article label including camera/time, ordered list semantics for frames, labelled buttons/textarea, `details` for facts, and polite/alert live regions.
- Preserve alt text that names the nominal sample offset without claiming an exact fall onset; provide an adjacent text timestamp/ID.
- Generated text is announced as advisory and visually separated from the detector evidence and human label.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated incident-detail panel for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable evidence panels, no 3D art or decorative charts. Show incident camera/time/ID, an observed chronological contact strip labelled 3 s before, 1.5 s before, At the alert with explicit saved/missing states, human decision controls, detector facts, a clearly advisory optional second-opinion block, and append-only history. Desktop 1440x1000 uses the authenticated shell; mobile 390x844 stacks frames and controls. All frame imagery is synthetic design-only unless labelled saved evidence; no post-alert frame, real patient, fabricated evidence, medical severity, emergency claim, or code.
```
