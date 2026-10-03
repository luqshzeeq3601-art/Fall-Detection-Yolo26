# P6-PAGE-DESIGN-AUDIT — Functionality audit and page design briefs

## Purpose
User-requested documentation follow-up to Phase 6: inspect current functionality, distinguish mocks and missing capabilities, and specify a consistent light redesign with a standalone image prompt for every page.

## Requirements
- Inspect working-tree code, including uncommitted frontend/backend work; old task reports are historical.
- Cover ten React routes, the not-found view, incident detail and the five Streamlit views.
- Create a shared design system, source-backed functionality audit, one Markdown brief per page, and an index.
- Each brief includes current functions, missing/mock boundaries, layout, interactions/states, responsive/accessibility rules, and a self-contained image prompt.
- Image prompts describe synthetic examples and do not assert benchmark, medical, or operational guarantees.

## Allowed files
New files in `docs/design/page-redesign/`, this brief, task report/review; coordinator may append `docs/planning/PROGRESS.md` only.

## Inputs/interfaces
TASK_SKILL_MATRIX.md P6-REDESIGN-PAGES and P6-REDESIGN-GATE; frontend/src, app/, streamlit_app.py, src/eldercare/api and live; existing mockups and planning specifications.

## Expected outputs
Reviewable documentation only. No application implementation, generated images, data/model changes, commits, pushes or deployment. Existing user edits and supplied images preserved.

## Skills to use
User-invoked frontend-design. Follow project fresh-worker/reviewer sequence with native Codex agents. Superpowers skill files were not found in the installed skill directories; use the repository's explicit task brief, review and verification process without installing another router. The prior scoped no-commit instruction is retained.

## Acceptance criteria
Every route/view has a brief and image prompt; all prompts share exact palette/type/shell; supported versus demo versus missing claims have source evidence; no invented operational metrics; links resolve; independent review has no unresolved Critical/Important findings.

## Tests required
Documentation coverage/link/provenance checks; source inspection and appropriate existing functionality tests where feasible. Browser/GPU validation must be reported separately from code inspection.

## Forbidden scope
New backend/UI features, model tuning, dataset access or redistribution, emergency escalation, medical diagnosis, automatic publication or commits.

## Report path
docs/task-reports/P6-PAGE-DESIGN-AUDIT.md
