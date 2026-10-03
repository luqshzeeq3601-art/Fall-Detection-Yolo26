# P6-AUTH-LANDING-SCALE

- User scope: sign-in and signup are too large at 1920x1080; match the landing page's UI scale. Continue direct coordinator work with no subagents.
- Task matrix: scoped continuation of P6-SIGNIN-FULLHD-REFERENCE and P6-SIGNUP-REFERENCE. Existing native CSS, typography and approved design specialist guidance apply; no new artwork or router.
- Baseline: landing header 64px, wordmark 18.5px, controls 44px, content container 1560px. Auth desktop uses 76-80px headers, 27-28px branding and 600px form cards.
- Change: reduce desktop auth headers/branding, 460px form cards, form text/padding/control size, signup feature-panel dimensions and signup content container. Remove sign-in forced 700px minimum form height. Preserve mobile 16px input fonts, native controls and layout containment.
- Preserve: artwork/color palette, auth API/validation/consent, signup role removal, signin setup-aware links and Google removal, landing page and all unrelated work.
- Acceptance: Full HD forms and actions fit with substantial surrounding space; header branding matches landing metrics; no horizontal overflow at desktop/tablet/mobile; relevant auth/accessibility tests, typecheck, component checks and build pass; screenshots visually inspected.
