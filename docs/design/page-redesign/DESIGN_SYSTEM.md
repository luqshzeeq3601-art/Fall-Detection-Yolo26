# ElderCare Vision page redesign design system

## 1. Scope and status vocabulary

- This document is a design proposal for the React routes and five Streamlit views.
- It describes the current source surface; it does not implement UI, change runtime behavior, or prove a browser, camera, GPU, or backend run.
- Use these labels in briefs and review notes:
  - `code-present (runtime unverified)`: a route, component, API boundary, or view exists in the current tree; live operation still needs runtime evidence.
  - `demo/mock`: deterministic `MockApiClient`, fixture transport, sample media, or explicitly synthetic artwork.
  - `partial`: the source supports part of the described behavior but lacks a needed path, state, or evidence.
  - `absent`: no current source path or endpoint was found.
  - `proposed`: redesign direction or a required repair, not an existing claim.

## 2. Visual thesis

- Subject: an evidence-led local fall-detection workbench for care operators and engineers.
- Direction: cool clinical daylight with a quiet instrument-panel rhythm. Solid white panels carry the work; blue and mint glass accents appear only in public artwork or a restrained signature strip.
- The memorable element is the observed temporal evidence contact strip: a compact chronological sequence with source-accurate labels `3 s before` → `1.5 s before` → `At the alert`. It does not imply a post-alert frame or the exact onset of a transition. It may show only saved frames or an explicit missing-frame state; it never invents a frame.
- Operations use hierarchy, timestamps, identifiers, status, and clear actions. No 3D art, decorative charts, fake health percentages, or unqualified reliability claims in authenticated views.

## 3. Exact tokens

### 3.1 Colour

| Token | Value | Use |
| --- | --- | --- |
| `canvas` | `#F3F7FA` | App background and page gutters |
| `surface` | `#FFFFFF` | Cards, forms, table rows, readable panels |
| `text` | `#142B3C` | Headings, primary labels, strong values |
| `muted` | `#526675` | Supporting copy, timestamps, helper text |
| `border` | `#D7E3EA` | Dividers, input borders, panel boundaries |
| `primary` | `#245DDA` | Main action, links, active navigation, focus ring basis |
| `mint` | `#DDF3EE` | Soft positive background and public accent field |
| `teal` | `#126B5A` | Positive text/icon on `mint` |
| `amber-bg` | `#FFF1D6` | Caution background |
| `amber` | `#8A5A00` | Caution text/icon on `amber-bg` |
| `red-bg` | `#FDECEF` | Error and confirmed-alert background |
| `red` | `#B42332` | Error and confirmed-alert text/icon on `red-bg` |

- Keep text contrast readable on every surface. Do not use colour alone for a status; pair it with a label and, where useful, an icon.
- If a neutral disabled state needs colour, use `muted` and `border`; do not introduce a new semantic colour.

### 3.2 Type

- Headings: `Sora`, proposed display face; it is not currently bundled and should be added as a local/licensed asset in a later implementation, with no external font fetch. Use a restrained weight range and sentence case.
- Body/UI: existing locally bundled `Plus Jakarta Sans` (`frontend/src/assets/plus-jakarta-sans.ttf`).
- IDs, timestamps, units, model/config versions, and code: `IBM Plex Mono`, proposed utility face; it is not currently bundled and should be added as a local/licensed asset in a later implementation, with no external font fetch. Keep a readable fallback stack.
- Suggested hierarchy: page title 32/40, section title 20/28, card title 16/24, body 15/24, metadata 12/18, utility 12/18. Adjust only when content density requires it.

### 3.3 Geometry and elevation

- Base spacing unit: `8px`; use 8, 16, 24, 32, 40, and 48px before inventing another value.
- Card radius: `16px`.
- Control radius: `10px`.
- Inputs and buttons: at least 44px tall on touch surfaces.
- Borders: 1px `border`; shadows are subtle, short, and used to separate a panel from `canvas`, not to make glass blur.
- Content max width: `1280px`; authenticated page padding: `32px` desktop.

## 4. Shell and navigation

- Authenticated desktop shell: `232px` sidebar plus `72px` top bar; the content column is capped at `1280px` and begins with `32px` padding.
- Navigation labels and order: Overview, Live monitor, Incidents, Review queue, Benchmarks, System health, Settings.
- Sidebar groups may be labelled Monitor, Respond, and System, but the visible page labels above remain stable.
- Top bar: global incident search, connection state, alert inbox, and operator menu. Search remains URL-addressable (`/app/incidents?search=...`).
- At widths below the tablet breakpoint, the sidebar becomes an accessible drawer with a visible close control, Escape dismissal, focus trap, and focus return to the menu button.
- Public routes use a compact header and two-column editorial layout where space allows; they do not use the authenticated sidebar.

## 5. Shared component grammar

- Page header: eyebrow only when it conveys a real category; title, one-sentence purpose, and one primary action.
- Panel: solid surface, clear title row, optional action, and a short state message when data is unavailable.
- Status: text plus icon/dot, with `mint/teal`, `amber-bg/amber`, `red-bg/red`, or neutral `border/muted` pairings.
- Evidence contact strip: three chronological slots derived from saved capture timestamps, labelled `3 s before`, `1.5 s before`, and `At the alert` (the current `KeyframeStrip` stores alert-first and captions the same offsets). Fewer than three frames show explicit missing slots; do not fabricate an `After` frame. Preserve source order and IDs in detail text.
- Tables and lists: align IDs and numeric units with IBM Plex Mono; keep camera name, time, state, and action visible before secondary metadata.
- Charts: use only when a measured series is present, include units and sample window, and provide a text/table equivalent. A single measured operating point is not a curve.
- Copy: sentence case, active verbs, exact action outcomes (`Save changes`, `Retry`, `Start monitoring`). Errors say what happened and the next action. Empty states explain how to create the next useful record.

## 6. Evidence and truth boundaries

- A detector decision is distinct from a human review and from optional generated text. Generated text never overwrites detector evidence or human labels.
- Local inference is the intended boundary for the detector, but it is not a blanket no-egress promise: an optional configured VLM may receive incident evidence images, uploaded videos are stored on the configured server, and `Record 10 s` is a manual browser download rather than automatic continuous recording. Keep these paths explicit wherever privacy is described.
- All media in redesign prompts is synthetic illustrative material unless it is explicitly described as a saved evidence asset. Prompts must never imply a real patient, a medical conclusion, or an operational guarantee.
- Benchmark pages may show values only when tied to a named artifact and split. Keep `59/60` recall, `59/(59+2)` event precision, `71/72` ADL true-negative clips, and the `0.83h` held-out false-alarm observation qualified as evaluation evidence. Do not present the held-out point estimate as a deployment gate pass; show its uncertainty/limited duration.
- Keep measured runtime telemetry separate from evaluation artifacts. `/ready` indicates API/database/manager readiness; `detector_ready`, stream freshness, and source state answer different questions.
- Do not reuse historical screenshots, mockups, or old copy as current runtime proof. The frontend browser report is historical evidence of UI checks, not a backend/camera/GPU validation.

## 7. Responsive and accessibility baseline

- Desktop reference: `1440 × 1000`; use the full shell and two-column workbenches where content permits.
- Mobile reference: `390 × 844`; collapse to one column, keep the primary action in the first viewport, make tabs horizontally scrollable or stacked, and preserve readable labels without horizontal overflow.
- Images use meaningful alt text or `alt=""` when decorative. Focus is visible with a 3px cobalt outline and 3px offset. Every icon-only control has an accessible name.
- Use semantic headings, landmarks, labelled inputs, `aria-live` for changing status, `aria-busy` for loading regions, and keyboard equivalents for queue decisions and tab lists.
- Respect `prefers-reduced-motion`; the live pulse may become a static dot and all transitions should be optional.

## 8. Page-prompt contract

- Every page brief contains a fenced image prompt that repeats the exact palette, type roles, spacing, radii, shell dimensions, and the page's requested content.
- Prompts are for synthetic design reference images only. They must specify `cool clinical daylight`, solid readable panels, no real people, no real patient data, no fabricated metrics, and no implementation/code output.
