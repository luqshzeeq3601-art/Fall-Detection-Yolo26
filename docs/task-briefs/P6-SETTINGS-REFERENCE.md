# P6-SETTINGS-REFERENCE — Account settings screenshot match

## Purpose
Match the supplied Account settings screenshot within the existing Phase 6 React dashboard.

## Requirements
Separate Account, Alerts on this device and Change password panels; horizontal profile details and password form on desktop; pale blue canvas and broad background arcs; navy text and blue controls with readable contrast. Reflow explicitly at tablet and mobile widths, including 320px, and verify Full HD 1920x1080. Keep real identity, role access, browser permissions, password API and team management.

## Allowed files
SettingsPage.tsx, SettingsPage.css, SettingsPage.test.tsx and scoped task/design/planning documentation. Preserve prior uncommitted edits. No backend, model, dataset, auth transport, dependency or shared-shell changes.

## Inputs and skills
User-selected frontend-design, image-to-code and design-taste-frontend. The user's screenshot controls the composition. A faithful built-in generated UI reference was inspected before coding; it is preview-only. Use existing local Plus Jakarta Sans and Lucide icons. Direct coordinator implementation, verification and review because the user expressly prohibited subagents. Reuse the existing checkout and leave changes uncommitted, consistent with the approved Phase 6 continuation.

## Acceptance
- Three primary panels match the reference; existing Team section remains below them.
- Name/email/role come from the signed-in account, not the screenshot.
- Unsupported profile editing is explained honestly, with no simulated save or new endpoint.
- Permission default/granted/denied/unsupported and workspace-off states remain clear; no permission request on mount.
- Password labels/autofill are preserved; visibility buttons are accessible; submission remains server-backed, reports errors, prevents duplicate submissions and clears secrets on success.
- No horizontal overflow, colliding controls or unreadable text at Full HD, laptop, tablet and mobile sizes.
- Focused tests, frontend typecheck/lint/tests/build and direct review pass. Record exact limitations.

## Verification
Focused Settings tests and complete frontend checks; real browser screenshot/DOM inspection, keyboard checks, contrast samples and responsive geometry. No real password change or notification permission grant during browser QA.

## Forbidden scope
New profile API, account mutations during visual QA, backend changes, public deployment, commits, other-page redesign or fabricated detector/evaluation claims.

## Reports
docs/task-reports/P6-SETTINGS-REFERENCE.md and docs/reviews/P6-SETTINGS-REFERENCE-review.md.
