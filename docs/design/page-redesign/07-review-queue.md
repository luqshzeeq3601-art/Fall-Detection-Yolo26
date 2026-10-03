# 07 — Review queue page (`/app/review`)

## 1. Purpose and source paths

- Purpose: let an operator review unreviewed incidents quickly, record an append-only human label, skip locally when needed, and revisit the session’s decisions.
- Current sources: [`frontend/src/pages/ReviewQueuePage.tsx`](../../../frontend/src/pages/ReviewQueuePage.tsx), [`frontend/src/features/review/reviewQueue.ts`](../../../frontend/src/features/review/reviewQueue.ts), [`frontend/src/components/incidents/KeyframeStrip.tsx`](../../../frontend/src/components/incidents/KeyframeStrip.tsx), [`frontend/src/hooks/useIncidents.ts`](../../../frontend/src/hooks/useIncidents.ts), [`frontend/src/hooks/useIncidentDetail.ts`](../../../frontend/src/hooks/useIncidentDetail.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), and [`src/eldercare/api/routers/incidents.py`](../../../src/eldercare/api/routers/incidents.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: unreviewed batch query, current case, saved keyframes, Real fall/False alarm/Unsure/Skip controls, F/N/U/S shortcuts, up-next list, session review list, and reviewed export.
- `code-present (runtime unverified)`: non-skip decisions POST append-only reviews; errors leave the current case available; queue refills when a batch is exhausted.
- `demo/mock`: fixture incidents and UI test API provide deterministic queue behavior; Skip is intentionally local session state.
- `partial`: Skip does not write a review or change the server queue; notes and full detector facts are available in incident detail rather than the queue card.
- `absent`: automatic retraining, bulk labelling, resident identity, escalation, and an evidence frame after alert are not present.

## 3. Proposed hierarchy

1. Header: Review queue, remaining count, shortcut legend.
2. Primary workbench: current incident metadata, observed chronological evidence strip, and decision bar.
3. Secondary rail: next five cases and decisions saved this session.
4. Decision confirmation: append-only label, optional note affordance, explicit saved/error feedback, and link to full details.
5. Completion state: explain whether the queue is empty or only skipped cases remain, with clear revisit action.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Review queue                         [18 waiting]  F/N/U/S shortcuts           │
│ ┌──────────────────────────────────────────────┐ ┌───────────────────────────┐ │
│ │ Current incident · camera · time · score     │ │ Up next                    │ │
│ │ [3 s before][1.5 s before][At the alert]    │ │ 2 camera · time · score   │ │
│ │ Was this a real fall?                        │ │ 3 ...                      │ │
│ │ [Real fall] [False alarm] [Unsure] [Skip]    │ │ Reviewed this session     │ │
│ │ Full details · save/error feedback            │ │ [Export] labels            │ │
│ └──────────────────────────────────────────────┘ └───────────────────────────┘ │

390 × 844
[menu] Review queue [18 waiting]
[current metadata]
[contact strip]
[decision buttons stacked]
[up next]
[reviewed this session]
```

## 5. Controls and states

- Controls: four labelled decisions, keyboard shortcuts F/N/U/S, Full details, Go through skipped ones, Export, and incident links in the reviewed list.
- Loading: queue and keyframes show separate loading states; decision buttons remain disabled until the selected detail matches the current ID.
- Empty: “Nothing waiting for review” links to Live monitor; “Only skipped incidents left” offers a local reset; “Nothing queued” is a normal rail state.
- Save error: use an alert with the returned message, keep the case and selected decision available, and do not advance the queue.
- Saving: only the selected button changes to `Saving…`; prevent duplicate submission; on success show the saved label and move to the next case.
- Missing evidence: keep three labelled slots and show `No keyframe saved` per missing slot; never add illustrative images to a real review workbench.
- Provenance: label Skip as `session only`; do not count it as a human review or export record.

## 6. Responsive and accessibility rules

- At 390px, decision buttons become full-width 44px controls and the current case remains before the queue rail.
- Keyboard shortcuts ignore inputs, textareas, dialogs, modifier keys, repeats, and focusable editable targets; show the legend in text.
- Use a named `main`, one `h1`, `aria-live` for save/error status, `aria-busy` for frame loading, and explicit radio/button names.
- Do not rely on image order or colour to communicate the label; use text and icons.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Review queue workbench for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no 3D art or decorative charts. Show waiting count, current incident metadata, a real-evidence placeholder strip labelled 3 s before, 1.5 s before, At the alert with explicit missing slots, Real fall/False alarm/Unsure/Skip controls, F/N/U/S legend, Up next rail, and Reviewed this session. Desktop 1440x1000 uses 232px sidebar + 72px top bar; mobile 390x844 stacks the current case and full-width decision buttons. All media is synthetic design-only; no real patients, invented evidence, fabricated metrics, emergency claims, or code.
```
