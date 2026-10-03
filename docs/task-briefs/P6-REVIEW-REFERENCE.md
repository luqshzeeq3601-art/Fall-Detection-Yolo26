# P6-REVIEW-REFERENCE — Review queue reference

## Purpose
Match the supplied review queue screenshot within the approved Phase 6 frontend scope.

## Requirements
- Pale blue background, navy readable typography, inline progress and shortcut legend, large evidence workbench and two side panels.
- R = real fall, F = false alarm, U = unsure, S = skip; ignore typing, modifiers, repeat and open dialogs.
- Show only saved evidence, preserve image aspect ratios, provide selection and explicit missing-image states. No invented playback or depth labels.
- Full HD desktop, laptop, tablet and 320–430px mobile reflow; 44px controls, visible focus, light/dark contrast.
- Note field with 500-character limit and count; skipped notes must not transfer to another incident.

## Allowed files
ReviewQueuePage, new ReviewQueueReference.css and ReviewEvidence component/tests, review shortcut helper/tests, focused queue tests, task/progress documentation.

## Inputs/interfaces
Existing incident/evidence ID-based URLs, immutable detector data, append-only submitReview API and containing app shell.

## Expected outputs
Functional screenshot-matched review UI; verification and direct review reports.

## Skills to use
User-selected frontend-design, image-to-code, design-taste-frontend; built-in imagegen for a preview reference only; installed browser controls.

## Acceptance criteria / tests
Selection/missing media/keyboard/note/error/skip regressions; typecheck, lint, frontend suite, production build; real browser checks at 1920x1080 and mobile; contrast and no overflow.

## Forbidden scope
No subagents (explicit user override), backend/model/dataset changes, new dependencies, fabricated operational media, commits/push/deployment or unrelated edits.

## Report path
docs/task-reports/P6-REVIEW-REFERENCE.md; docs/reviews/P6-REVIEW-REFERENCE-review.md.
