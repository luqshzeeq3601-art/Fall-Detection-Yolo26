# 16 — Streamlit benchmarks gate view (`results`)

## 1. Purpose and source paths

- Purpose: render the empirical evaluation metrics and deployment gate scorecard recorded from the sealed, post-freeze evaluation on unseen test videos (UP-Fall Test-B), documenting phase progression, per-camera breakdowns, and algorithmic boundary conditions.
- Current sources: [`streamlit_app.py`](../../../streamlit_app.py), [`app/views/benchmarks.py`](../../../app/views/benchmarks.py), [`app/core/data_loader.py`](../../../app/core/data_loader.py), [`docs/reports/V6_3_FINAL_TESTB_EVALUATION.json`](../../reports/V6_3_FINAL_TESTB_EVALUATION.json), and [`docs/reports/V6_FINAL_RESULTS.md`](../../reports/V6_FINAL_RESULTS.md).

## 2. Current functionality and boundaries

- `code-present (artifact-backed)`: Reads JSON reports directly from disk (`V6_3_FINAL_TESTB_EVALUATION.json` and per-phase development reports).
- `code-present (artifact-backed)`: Four headline gate metrics: Event-Level Recall (98.3% vs target ≥90%), Event-Level Precision (96.7% vs target ≥85%), p95 Time-to-Alert (1.58 s vs target ≤3.0 s), and Held-Out False Alerts (0.00 / hr over 0.83 h).
- `code-present (artifact-backed)`: Statistical uncertainty reporting including Wilson 95% confidence intervals on recall/precision and Poisson upper bound (3.59/h) on false alarms.
- `code-present (artifact-backed)`: Multi-angle camera breakdown table (Camera 1 vs Camera 2) showing evaluated falls, recall progress bar, precision progress bar, false alerts, and p95 TTA.
- `code-present (artifact-backed)`: Engineering phase progression table and bar chart tracking out-of-fold metrics across development milestones (Phase 0 through Phase 3b freeze).
- `code-present (runtime unverified)`: Bento card comparison of Critical Algorithmic Drivers vs Empirical Boundary Conditions.
- `partial`: Overall gate badge displays "Gate Target Met" based on the raw point estimate (0 false alarms in 0.83 h); redesign must qualify that 0.83 h of unscripted exposure does not provide sufficient statistical power to confirm the 0.05/h target with high certitude.
- `partial`: Explanatory text states "31 sequences across 2 cameras"; the underlying evaluation comprises 60 fall camera clips and 72 ADL camera clips. The reporting units (clips vs events) must be explicitly delineated.
- `absent`: Real-time benchmark execution runner, dynamic hyperparameter tuning interface, and external dataset upload evaluator.

## 3. Proposed hierarchy

1. View Header: Title `Benchmarks & Gate Scorecard`, empirical verification eyebrow, Gate Target Met / Qualified badge, and expandable metric glossary.
2. Sealed Test-B Scorecard: Four solid metric cards with delta targets and Wilson confidence intervals, explicitly noting the limited duration of false-alarm exposure.
3. Multi-Angle Evaluation Table: Per-camera performance breakdown (Camera 1 high-mount vs Camera 2 eye-level).
4. Engineering Phase Evolution: Milestone progression table and bar chart illustrating iterative gains across development phases.
5. Technical Breakthroughs & Limitations: Two-column balanced panel contrasting algorithmic improvements against empirical boundaries (sample size constraints, lab volunteer staging, unscripted duration limits).

## 4. Desktop and mobile wireframe

```text
1440 × 1000  Streamlit Shell [Sidebar: Brand · Status · Local privacy]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Benchmarks & Gate Scorecard   EMPIRICAL VERIFICATION · SEALED EVALUATION     │
│ Evaluation on sealed UP-Fall Test-B (frozen V6.3 model weights).             │
│ [v] Metric definitions & evaluation criteria (Expander)                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ SEALED TEST-B SCORECARD (Frozen V6.3)                                        │
│ ┌───────────────┬────────────────┬────────────────┬────────────────────────┐ │
│ │ Event Recall  │ Event Precision│ p95 Latency    │ Held-Out False Alerts  │ │
│ │ 98.3% (59/60) │ 96.7% (59/61)  │ 1.58 s         │ 0.00 / hr (0 in 0.83h) │ │
│ │ Target ≥ 90%  │ Target ≥ 85%   │ Target ≤ 3.0 s │ Target Unproven (≤3.59)│ │
│ └───────────────┴────────────────┴────────────────┴────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────┤
│ PER-CAMERA BREAKDOWN (Multi-Angle Evaluation)                                │
│ Camera Angle | Evaluated Falls | Recall (%) | Precision (%) | p95 TTA (s)    │
│ Camera 1     | 30              | [████ 100%] | [████ 96.8%] | 1.48 s        │
│ Camera 2     | 30              | [████ 96.7%]| [████ 96.7%] | 1.62 s        │
├──────────────────────────────────────────────────────────────────────────────┤
│ ENGINEERING EVOLUTION ACROSS PHASES (Development History)                    │
│ [Phase progression table & multi-bar chart comparing Cam 1 / Cam 2 / URFD]   │
├──────────────────────────────────────────────────────────────────────────────┤
│ TECHNICAL BREAKTHROUGHS & EMPIRICAL LIMITATIONS                              │
│ ┌──────────────────────────────────────┐ ┌─────────────────────────────────┐ │
│ │ Algorithmic Drivers: Multi-person    │ │ Empirical Boundaries: 31 events,│ │
│ │ pose tracking, inertia re-ID,        │ │ healthy volunteers, 0.83h home  │ │
│ │ normalized vertical velocity.        │ │ stream requires longitudinal exp│ │
│ └──────────────────────────────────────┘ └─────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844  Streamlit Mobile
[Menu] Benchmarks Scorecard
[Recall: 98.3%] [Precision: 96.7%]
[p95 TTA: 1.58s] [FA: Unproven]
[Per-Camera Table (Scrollable)]
[Phase Evolution Chart]
[Algorithmic Drivers Card]
[Empirical Boundaries Card]
```

## 5. Controls and states

- Controls: Metric definition expander toggle, dataframe column sorting, phase chart view.
- Loaded State: Renders verified metric cards with green delta tags for recall/precision/latency; false-alarm card explicitly includes statistical interval text.
- Missing Report Warning: If `V6_3_FINAL_TESTB_EVALUATION.json` is missing, renders an amber warning banner (`Final evaluation report artifact missing`) and suppresses scorecard cards.
- Gate Uncertainty Handling: Clarify that while the observed false alarm count is 0, the target (≤0.05/h) is labeled `Target unproven` due to 0.83 h sample window.
- Historical Data Representation: Clearly separate sealed Test-B metrics from developmental out-of-fold iterations to avoid confusion regarding evaluation splits.

## 6. Responsive and accessibility rules

- At 390px, stack the four metric cards into a 2x2 grid or vertical layout; format tables with horizontal scrolling or vertical cards; preserve column headers.
- Provide accessible text labels for progress bar columns in the camera breakdown table.
- Maintain high contrast on all chart series (Cobalt `#245DDA`, Teal `#126B5A`, Amber `#8A5A00`).
- Ensure all technical abbreviations (p95, TTA, ADL, CI, OOF) have explanatory expansions in tooltips or the definition expander.

## 7. Synthetic image prompt

```text
Design a synthetic Streamlit benchmark gate scorecard reference for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white cards with crisp borders, no translucent glass blur or 3D art. Top area displays “Benchmarks & Gate Scorecard” with a green “Gate Target Met (Qualified)” pill and an expander toggle for metric definitions. Main section features four solid cards: Event Recall 98.3% (Target >= 90%), Event Precision 96.7% (Target >= 85%), p95 Latency 1.58 s (Target <= 3.0 s), and Held-Out False Alerts 0.00 / hr with a cautionary note “Target unproven due to 0.83h exposure”. Below is a clean camera comparison table with progress bars, a milestone bar chart showing recall gains across phases, and a two-column panel contrasting algorithmic drivers with empirical boundaries. Desktop 1440x1000; mobile 390x844 stacks cards. Synthetic benchmark graphics only, no code.
```
