# P6-INCIDENTS-REFERENCE — Incidents screenshot match

## Purpose
Match the user-supplied Incidents reference while preserving operational data and review behavior.

## Requirements and acceptance
- Phase 6 rows P6-003, P6-004, P6-005 and P6-008; AC-041 through AC-044.
- Pale blue canvas, navy readable typography, four summary cards, blue active tab, filter band, balanced queue/detail panels.
- Full HD 1920x1080 and mobile 320–430px: no page overflow or control collisions; touch targets at least 44px.
- Real evidence thumbnails only; missing/unavailable evidence must be explicit. No invented playback, duration or chart results.
- Preserve server filters, URL selection/pagination, signed-in reviews, export permissions, optional generated-context labels, response actions and research boundary.

## Allowed files
IncidentsPage.tsx, new IncidentsReference.css and queue-preview component/tests, IncidentsAndReview.test.tsx, asset attribution and these task records/planning updates. Shared component behavior and backend contracts remain unchanged.

## Skills and execution
User-selected frontend-design, image-to-code and design-taste-frontend. Built-in imagegen creates decorative canvas before implementation. Screenshot overrides generic landing-page styling rules. User explicitly prohibits subagents: direct coordinator implementation, verification and review. Preserve existing uncommitted work; do not stage whole modified files containing unrelated changes.

## Verification
Behavior tests for filter submission, thumbnail evidence/fallback, selection/review, keyboard tabs; frontend lint/typecheck/build; browser geometry, contrast, desktop/mobile screenshots and selected/empty states.

## Report
docs/task-reports/P6-INCIDENTS-REFERENCE.md
