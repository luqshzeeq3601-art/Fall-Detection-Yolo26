# Signup without role selection

Date: 2026-10-03. Direct coordinator implementation and review; no subagents.

- Removed the complete account-role area, both caregiver/admin cards, assignment note and indicators. Removed unused role icons, signup setup-status lookup, the accountRole component slot and related desktop/mobile CSS. Confirm password now flows directly to consent and Create account.
- Retained the reference feature panel, synthetic camera/pose/ribbon background, native form controls, Plus Jakarta Sans and readable navy/blue colors. The compact form centers naturally on Full HD; phone layout remains form-first. Existing pale surfaces and contrast tokens are unchanged.
- Signup API payload, server permission rules, validation, consent defaults and error handling are preserved. No real account was created. Regression coverage now verifies role UI is absent for both setup-status fixtures; mocked signup still verifies no requested job_role is sent.
- Typecheck PASS; scoped ESLint PASS; 6 relevant test files / 27 tests PASS; production build PASS; scoped diff check PASS.
- Eleven browser sizes (1920x1080, 1586x992, 1366x768, 1100x820, 1000x800, 768x1024, 844x390, 430x932, 390x844, 360x800, 320x568) passed horizontal overflow and header/card/control bounds checks. Zero role cards/radios at all sizes, inputs 16px. Full HD and 1586x992 views fit vertically; smaller screens scroll naturally.
- Mobile empty-submit check: five existing field/consent errors, zero role cards and no horizontal overflow. Desktop and phone viewport screenshots inspected. Full-page capture was unavailable; viewport capture succeeded through the documented browser API. Evidence: frontend/output/playwright/signup-no-roles/fullhd.jpg, mobile.jpg, viewports.json. Screenshots show the visible viewport; DOM geometry confirms the complete Full HD layout fits.
- Direct review: no unresolved Critical/Important scoped findings. No independent reviewer claimed. No new assets, dependencies, backend, models, datasets or benchmark edits. Existing user work retained. No commit, push or deployment.

Preview: http://127.0.0.1:5176/signup.
