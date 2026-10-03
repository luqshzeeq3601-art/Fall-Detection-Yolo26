# 06 — Incidents page (`/app/incidents`)

## 1. Purpose and source paths

- Purpose: find detector-confirmed incidents, filter them by review state/camera/time/search, inspect one detail panel, and export reviewed records.
- Current sources: [`frontend/src/pages/IncidentsPage.tsx`](../../../frontend/src/pages/IncidentsPage.tsx), [`frontend/src/pages/OperationsPages.css`](../../../frontend/src/pages/OperationsPages.css), [`frontend/src/components/incidents/IncidentDetail.tsx`](../../../frontend/src/components/incidents/IncidentDetail.tsx), [`frontend/src/hooks/useIncidents.ts`](../../../frontend/src/hooks/useIncidents.ts), [`frontend/src/hooks/useIncidentDetail.ts`](../../../frontend/src/hooks/useIncidentDetail.ts), [`frontend/src/api/client.ts`](../../../frontend/src/api/client.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), and [`src/eldercare/api/routers/incidents.py`](../../../src/eldercare/api/routers/incidents.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: URL-addressable tabs for All, Needs review, Real falls, and False alarms; camera/search/date filters; clear filters; offset pagination; row selection; detail panel; JSONL export.
- `code-present (runtime unverified)`: API filtering supports camera, detector status, review label, reviewed/unreviewed, text query, time bounds, limit, offset, and cursor; detail fetch is keyed to the selected ID.
- `demo/mock`: `MockApiClient` provides deterministic incidents, evidence, enrichments, filters, pagination, and append-only reviews for UI tests.
- `partial`: rows expose detector score and latest review, while full evidence/facts/actions are in a companion panel; there is no bulk review or advanced sort control.
- `partial`: evidence can be absent and must remain explicit; generated second opinion is optional and distinct from detector evidence.
- `absent`: incident escalation, real-time stream playback inside the list, and arbitrary evidence-path access are not present.

## 3. Proposed hierarchy

1. Header: Incidents, one-sentence purpose, Export reviewed.
2. Filter band: review tabs, search, camera, From/To, clear filters; show active filter chips and result count.
3. Main workbench: dense but readable incident list on the left and the selected detail panel on the right.
4. Row priority: camera, confirmed time, detector score, review state, open/selection affordance.
5. Detail panel: observed temporal evidence contact strip, human decision bar, optional second opinion, detector facts, review history.
6. Pagination/footer: current range and next/previous with preserved URL state.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Incidents                                      [Export reviewed]              │
│ [All] [Needs review] [Real falls] [False alarms] [search] [camera] [dates]  │
│ ┌───────────────────────────────┐ ┌────────────────────────────────────────┐ │
│ │ 12 incidents                  │ │ Incident · camera · timestamp          │ │
│ │ row camera | time | score | tag│ │ [3 s before][1.5 s before][At alert]   │ │
│ │ row ...                       │ │ decision bar + optional note          │ │
│ │ [prev] 1 / 2 [next]           │ │ facts · second opinion · history       │ │
│ └───────────────────────────────┘ └────────────────────────────────────────┘ │

390 × 844
[menu] Incidents [Export]
[filter tabs →]
[search][camera][dates]
[incident rows]
[selected detail opens below / full panel]
```

## 5. Controls and states

- Controls: review tabs, search (debounced into URL), camera select, date inputs, Clear filters, incident row buttons, pagination, Export reviewed, detail decisions and note.
- Loading: keep the list shell and show `Loading incidents…`; selected detail has its own loading state and must not reuse a previous incident’s evidence.
- Empty: distinguish `Nothing waiting for review`, `No incidents match`, and `No keyframes were saved for this incident`; provide clear filters or Live monitor route.
- Error: list/detail/export errors identify the failed action with Retry; a failed review save leaves the selected incident and note available.
- Stale: if a future live refresh updates a list, display last refresh time; do not silently move selection or page.
- Evidence: show exactly the saved frames in chronological contact-strip order (`3 s before → 1.5 s before → At the alert`); fewer frames show missing slots.

## 6. Responsive and accessibility rules

- At 390px, filters collapse behind a labelled button or horizontal scroller; list rows precede the detail panel and selection opens an in-page detail heading.
- Use `role="tablist"` for review filters, `aria-selected`/`aria-pressed` for state, row buttons with camera/time names, and visible focus.
- Keep IDs/times/scores in IBM Plex Mono with text labels; use a table/list equivalent for any score visualization.
- Preserve query parameters on refresh and back/forward navigation; do not require pointer-only row selection.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Incidents workbench for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no 3D art or decorative charts. Show a 232px sidebar, 72px top bar, filter tabs/search/camera/date controls, a dense incident list, and a selected detail panel with an observed temporal contact strip labelled 3 s before, 1.5 s before, At the alert, explicit missing-frame slots, human decision buttons, optional generated text clearly separated, detector facts, and review history. Desktop 1440x1000; mobile 390x844 stacks list then detail. All images are synthetic placeholders, no real patients, no invented evidence, no fabricated reliability metrics, no medical guarantees, no code.
```
