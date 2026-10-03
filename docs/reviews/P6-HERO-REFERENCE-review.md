# P6-HERO-REFERENCE review

Date: 2026-10-03
Scope: LandingPage.tsx, LandingPage.css, hero-reference-v2.png, ASSETS.md and the scoped task/source planning entries. Existing auth changes excluded. Read-only production review; only this report was written.

## Verdict

Approve code scope with one minor CSS correction recommended. Final visual acceptance remains conditional on the coordinator's browser verification; no screenshots were available in frontend/output/playwright/hero-reference at review time.

## Findings

- Critical: none.
- Important: none found in the inspected diff.
- Minor: frontend/src/pages/LandingPage.css mobile subtitle rule uses `.landing-hero-subtitle`, which cannot override the desktop `.landing-page .landing-hero-subtitle`. At mobile widths the intended 17px/1.5 remains 18px/1.45. Match selector specificity if the smaller mobile typography is intended.

## Evidence and boundaries

- Compared the supplied 1774x887 reference and generated transparent asset visually. The asset reproduces camera, phone, blue/mint ribbons and integrated evidence sequence; visible synthetic labeling and descriptive alt text identify its illustrative purpose.
- Removed placeholder evidence geometry cleanly; no new dependencies or runtime logic added.
- Signed-in/signed-out CTA destinations, anchor links and targets, and BENCHMARK interpolation remain unchanged in the scoped TSX diff.
- Scoped headline/subtitle/primary-button/header-button selectors win against Polish.css. Global link focus-visible styling remains available; reduced-motion rules remove button transforms/transitions.
- Mobile navigation hiding predates this change. Header wrapping and 44px minimum action rules support narrow screens, but actual overflow, screenshot proportions and interactions require browser evidence.
- No detector performance numbers were introduced or altered. Existing research wording is preserved. Asset documentation explicitly says frames/labels/times are illustrative.
- No secrets, private paths or external asset dependencies introduced in the inspected production diff.
- ASSETS.md's shared historical prompt says no words/numbers while the new dated row explicitly describes text-bearing artwork; the row is sufficiently specific, though historical prompt wording could be clarified in future documentation cleanup.

No tests or browser execution were performed by the original reviewer. Test-engineer and coordinator evidence must establish final acceptance.

## Coordinator final review after user delegation override

The user requested no subagents, and active workers were stopped. The coordinator completed the remaining changes and final review directly. The subtitle selector specificity and historical asset prompt wording were corrected. Browser inspection also prompted a tablet header correction to preserve the wordmark, a narrower phone heading scale, and horizontal artwork spacing to separate the decorative sphere from paragraph text.

Final visual and interaction checks passed across nine viewport sizes; final typecheck, lint, 82 tests and build passed. Evidence: `docs/task-reports/P6-HERO-REFERENCE-verification.md`. No unresolved Critical or Important findings remain. Coordinator accepts the scoped hero change as a close reproduction of the supplied reference; generated artwork and the existing local typeface are not pixel-identical.
