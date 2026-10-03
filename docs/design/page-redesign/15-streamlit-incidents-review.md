# 15 — Streamlit incidents review view (`incidents`)

## 1. Purpose and source paths

- Purpose: provide a human-in-the-loop audit console to review fall events registered by the local engine, inspect synchronized 3-keyframe evidence, consult advisory vision-language model (VLM) opinions, submit ground-truth labels, and export a fine-tuning dataset.
- Current sources: [`streamlit_app.py`](../../../streamlit_app.py), [`app/views/incidents.py`](../../../app/views/incidents.py), [`app/components/agent_drawer.py`](../../../app/components/agent_drawer.py), [`app/components/cards.py`](../../../app/components/cards.py), [`app/core/backend.py`](../../../app/core/backend.py), and [`src/eldercare/incidents/repository.py`](../../../src/eldercare/incidents/repository.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: Queue metrics strip: Total Incidents, Awaiting Audit, AI Divergence (cases where vision model expressed uncertainty or disagreement), and Verified & Cleared.
- `code-present (runtime unverified)`: Incident filtering via segmented control: `Waiting for review`, `Flagged by AI`, `Reviewed`, `All`, with a manual refresh button.
- `code-present (runtime unverified)`: Incident selection dropdown listing timestamp, camera identifier, and current audit state.
- `code-present (runtime unverified)`: Chronological 3-frame evidence strip displaying pre-fall posture (`3.0s Prior`), descent inception (`1.5s Prior`), and alert onset (`Alert Moment T=0`).
- `code-present (runtime unverified)`: Advisory AI second opinion expander rendering VLM scene description, posture evaluation, and environmental hazard notes without overriding detector decisions.
- `code-present (runtime unverified)`: Caregiver verification form: ground-truth classification radio (`Fall`, `Not a fall`, `Unsure`), reviewer identifier, observation notes, and append-only database persistence.
- `code-present (runtime unverified)`: Verification audit trail detailing timestamped past reviews with reviewer identity and rationale.
- `code-present (runtime unverified)`: Training corpus export: downloadable `reviewed_incidents.jsonl` packaging 3 keyframes, raw model confidence scores, VLM context, and caregiver labels.
- `partial`: Keyframes display is read-only image cards; there is no frame scrubber, pan/zoom, or raw video playback within the Streamlit incident view.
- `partial`: Reviewer identifier is an unauthenticated text field rather than an authenticated user profile session.
- `absent`: Direct batch approval actions, automated notification webhook triggers, and cloud synchronization.

## 3. Proposed hierarchy

1. View Header: Title `Incidents & Review`, human-in-the-loop audit eyebrow, Audit Console badge, and queue objective.
2. Queue Summary KPI Cards: Four solid metric cards (Total Incidents, Awaiting Audit, AI Divergence, Verified & Cleared).
3. Queue Filter & Incident Selector: Filter tabs (`Waiting for review`, `Flagged by AI`, `Reviewed`, `All`) with Refresh button, followed by an incident selector card.
4. Main Inspection Split:
   - Left (62% width): Incident metadata (timestamp, camera ID, confidence score), Chronological Evidence Strip (3-frame cards), and Advisory AI Second Opinion panel.
   - Right (38% width): Caregiver Verification Form (ground truth radio, reviewer ID, notes, primary submit button) and historical audit trail list.
5. Export Section: Dataset Flywheel banner with verified record count and Download Verified Corpus button.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  Streamlit Shell [Sidebar: Brand · Status · Local privacy]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Incidents & Review      HUMAN-IN-THE-LOOP AUDIT · DATASET FLYWHEEL           │
│ [Total: 14]       [Awaiting Audit: 3]     [AI Divergence: 1]  [Cleared: 10]  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Filter: [ (Waiting for review) | Flagged by AI | Reviewed | All ]  [Refresh] │
│ Select Incident: [02 Oct 2026, 14:22:05 · Camera: demo-urfd · Waiting   ▼]   │
├─────────────────────────────────────────┬────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │ ┌────────────────────────────────┐ │
│ │ Incident #inc-48a2 · 14:22:05       │ │ │ CAREGIVER VERIFICATION         │ │
│ │ Camera: demo-urfd · Score: 94%      │ │ │ Ground truth:                  │ │
│ │ ┌───────────┬───────────┬─────────┐ │ │ │ (o) True Fall  ( ) False Alarm │ │
│ │ │ 3.0s Prior│ 1.5s Prior│ Alert   │ │ │ │ ( ) Unsure                     │ │
│ │ │ [Frame 1] │ [Frame 2] │[Frame 3]│ │ │ │ Reviewer ID: [Nurse Kelly    ] │ │
│ │ └───────────┴───────────┴─────────┘ │ │ │ Notes: [Patient slid from bed ] │ │
│ │ ┌─────────────────────────────────┐ │ │ │ [ Submit Verification (Cobalt) ]│ │
│ │ │ Advisory AI Second Opinion      │ │ │ ├────────────────────────────────┤ │
│ │ │ VLM: "Subject seated on floor,  │ │ │ Audit Trail:                     │ │
│ │ │ rapid descent verified."        │ │ │ - Verified: True Fall by NK      │ │
│ │ └─────────────────────────────────┘ │ │ └────────────────────────────────┘ │
│ └─────────────────────────────────────┘ │                                    │
├─────────────────────────────────────────┴────────────────────────────────────┤
│ TRAINING CORPUS PIPELINE                                                     │
│ Verified incidents package keyframes & labels for retrain. [Download JSONL]  │
└──────────────────────────────────────────────────────────────────────────────┘

390 × 844  Streamlit Mobile
[Menu] Incidents & Review
[Awaiting: 3] [Cleared: 10]
[Filter: Waiting | Reviewed]
[Incident Selector Dropdown]
[Chronological 3 Keyframes Stacked]
[Advisory AI Opinion Card]
[Verification Radio & Submit Form]
[Download Verified Corpus Button]
```

## 5. Controls and states

- Controls: Segmented filter tabs, refresh button, incident selector selectbox, ground-truth radio buttons, reviewer text input, notes textarea, Submit Verification button, Download JSONL button.
- Empty Queue State: If no incidents exist, render an empty-inbox container with a direct button link to `Launch Live Demo`.
- Filter Empty State: If no incidents match the chosen filter, show an informational note (`No incidents match filter: Flagged by AI`) and retain the export section.
- Missing Keyframe State: If an individual snapshot file is missing from disk, show a distinct warning slot (`Snapshot missing: 1.5s Prior`) rather than an empty broken image.
- Form Submission State: Submitting writes the review, shows a success toast, refreshes the queue, and appends the entry to the audit trail.
- Export State: Download button is disabled if zero reviewed incidents exist; enabled as primary button with record count when reviews are present.

## 6. Responsive and accessibility rules

- At 390px, stack the 3 keyframes vertically or enable clean horizontal scrolling; position the verification form immediately after the frames so actions remain accessible.
- Label all radio choices with standard descriptive text (`True Fall`, `False Alarm`, `Unsure`).
- Keep audit notes and reviewer inputs keyboard-navigable and preserve screen-reader labels.
- Frame captions must explicitly state their chronological relationship to the alert (`3.0s Prior`, `1.5s Prior`, `Alert Moment`).

## 7. Synthetic image prompt

```text
Design a synthetic Streamlit incident review console reference for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white cards with crisp borders, no translucent glass blur or floating 3D graphics. Show a Streamlit layout with four summary KPI cards at the top (Total 14, Awaiting Audit 3 in amber, AI Divergence 1 in violet, Cleared 10 in mint). A filter bar shows “Waiting for review” active. Left panel features an incident card for #inc-48a2 with three synchronized rectangular video snapshot frames in chronological order (3.0s prior, 1.5s prior, alert moment), followed by a subdued card for advisory AI second opinion. Right panel features a clean verification form with radio buttons for True Fall / False Alarm / Unsure, text field for reviewer, notes box, and a solid cobalt “Submit Verification” button, plus a short audit history below. Bottom card offers a training corpus export button. Desktop 1440x1000; mobile 390x844 stacks elements. Synthetic demonstration graphics only, no real patient photos, no code.
```
