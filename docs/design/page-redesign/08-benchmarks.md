# 08 — Benchmarks page (`/app/benchmarks`)

## 1. Purpose and source paths

- Purpose: present the frozen V6.3 evaluation as a traceable evidence page, with metric units, gates, sample limits, and links to the source report.
- Current sources: [`frontend/src/pages/BenchmarksPage.tsx`](../../../frontend/src/pages/BenchmarksPage.tsx), [`frontend/src/features/benchmarks/BenchmarkCharts.tsx`](../../../frontend/src/features/benchmarks/BenchmarkCharts.tsx), [`frontend/src/api/benchmarkData.ts`](../../../frontend/src/api/benchmarkData.ts), [`docs/reports/V6_3_FINAL_TESTB_EVALUATION.json`](../../reports/V6_3_FINAL_TESTB_EVALUATION.json), [`docs/reports/V6_FINAL_RESULTS.md`](../../reports/V6_FINAL_RESULTS.md), and [`app/views/benchmarks.py`](../../../app/views/benchmarks.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: static V6.3 snapshot cards, source report link, activity results, time-to-alert dots, and development-history presentation.
- `code-present (artifact-backed)`: the snapshot records 59/60 fall clips/events detected, 2 false-alert events for event precision 59/(59+2) ≈ 96.7%, p95 onset-to-alert 1.579 s, and 71/72 ADL clips quiet; held-out longform is about 0.83 h with 0 observed alerts and a 95% upper bound about 3.59/h.
- `partial`: current React visuals contain unsupported V6.2 deltas, decorative literal sparklines, an invented PR curve, incorrect no-fall cells (3.3%/96.7%), unsupported runtime tiles, a future date, and a dead dataset-selector control. These are redesign defects to remove, not facts to repeat.
- `demo/mock`: all current React values are a static snapshot; development history is not a matched sealed-version comparison. Streamlit reads local artifacts but still needs runtime qualification.
- `proposed`: show one measured operating point and a clip/event-unit table; label `False-alarm target unproven` rather than a deployment gate pass.

## 3. Proposed hierarchy

1. Header: Model results, frozen model/split/date/commit chips, and report link.
2. Gate summary: Recall, event precision, p95 time-to-alert, and false-alarm evidence as four source-linked cards.
3. Evidence table: unit, numerator/denominator, source split, interval/qualification, and gate status.
4. Activity/camera breakdown: compact tables for 59/60 fall clips, 1/72 ADL alerts, and per-camera counts; no unsupported curves.
5. Time-to-alert distribution: measured 59-dot strip or table with median/p95, clearly marked as Test-B evidence.
6. Limitations: different recordings of development subjects, staged laboratory context, and limited 0.83 h longform exposure.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Benchmarks             V6.3 · UP-Fall Test-B · 2026-10-01 · [source report]  │
│ [Recall 59/60] [Event precision 59/(59+2)] [p95 1.579 s] [FA target unproven]│
│ ┌──────────────────────────────────────────────────────────────────────────┐ │
│ │ Evidence table: metric | unit | value | gate | interval/qualification     │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ [fall clip table] [ADL clip table] [camera breakdown]                          │
│ [measured alert-time strip/table]                                              │
│ [limitations + artifact provenance]                                            │

390 × 844
[menu] Benchmarks [report]
[four evidence cards stacked]
[metric table scrolls vertically]
[activity/camera tables]
[alert-time list]
[limitations]
```

## 5. Controls and states

- Controls: source-report link, artifact/provenance disclosure, optional accessible table sort only when a real data set is present. The single snapshot is a static provenance chip, not a fake dataset selector.
- Loading: if the snapshot is fetched later, show skeleton cards and a source timestamp; no zero fallback.
- Error/absent artifact: say which report is missing and show `Evaluation unavailable`; keep the page usable for methodology/limitations.
- Empty: show `No measured operating point loaded`, not an empty chart or fabricated pass.
- Qualification: separate event-level precision from clip-level ADL specificity; explain that Test-B recordings are new recordings of subjects seen during development diagnostics.
- Gate state: Recall/precision/p95 can show their artifact comparison; false-alarm state remains `Target unproven` because 0.83 h and the 3.59/h upper bound do not establish 0.05/h.
- Runtime metrics: do not show current FPS/GPU/CPU values here; link to System health when the current host supplies them.

## 6. Responsive and accessibility rules

- At 390px, stack evidence cards and turn tables into labelled vertical records; keep source split and unit in every row.
- Every visual distribution has a text table/list alternative and explicit units; no chart communicates an unsupported threshold sweep.
- Use headings, captions, `scope`/labels for tables, and a text gate status; expose commit/date as selectable monospace text.
- Avoid red/green-only pass semantics; pair with `Measured`, `Qualified`, `Unavailable`, or `Target unproven` text.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Benchmarks evidence page for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no decorative glass or unsupported curves. Show V6.3, UP-Fall Test-B, artifact date 2026-10-01, report link, four qualified evidence cards for 59/60 recall, event precision 59/(59+2), p95 1.579 seconds, and “False-alarm target unproven”; show clip/event unit tables, measured alert-time distribution, and limitations. Desktop 1440x1000 with 232px sidebar + 72px top bar; mobile 390x844 stacks cards/tables. Use synthetic placeholders only, no real patient data, no invented trends, no deployment-gate pass, no code.
```
