# P6-RESPONSIVE-TYPE — Full HD and mobile typography

## Purpose
User requests suitable font sizes for the landing and sign-in pages on Full HD desktop and mobile. Scoped Phase 6 follow-up using the existing approved reference design.

## Scope
LandingPage.css and SignInPage.css typography and necessary wrapping/control spacing only. Preserve content, illustrations, routes, auth logic, signup styles, benchmark values and privacy qualifications. No new asset/dependency, deployment or commit.

## Acceptance
At1920x1080: clear display hierarchy, landing primary actions visible, complete sign-in form actions within viewport. At mobile320/360/375/390/430 widths: no overflow, clipped text or colliding controls; sign-in inputs at least16px, body16px where appropriate, form labels/actions14px or larger, utility text13px or larger where space allows. Mobile headings32–40px landing and32px sign-in. Preserve contrast,44px touch actions and keyboard focus. Include a960x540 reduced CSS viewport reflow probe; do not claim actual browser zoom was emulated.

## Verification
Inspect baseline computed styles/screenshots before editing, then verify desktop/tablet/mobile renders, control geometry, form validation/password visibility, anchors/CTA/focus. Run frontend typecheck/lint/tests/build and diff check. Changes are layout-only; use existing meaningful tests and runtime checks rather than duplicating CSS rules in unit tests.

## Execution
Coordinator only; user explicitly prohibits all subagents. Existing design skills already read this conversation. No new image generation needed for this typography adjustment. Update PROGRESS after verified completion, leave changes uncommitted.
