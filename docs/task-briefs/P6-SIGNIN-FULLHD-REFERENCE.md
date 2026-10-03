# P6-SIGNIN-FULLHD-REFERENCE

- User request: match the newly supplied 1920x1080 sign-in reference, readable text, Full HD/mobile compatibility, no subagents.
- Same user-selected frontend-design, image-to-code and design-taste-frontend skills. Reuse the matching built-in-imagegen scene already generated and inspected in this conversation. No new bitmap is needed for unchanged reference artwork.
- Findings: current CSS shrank the desktop card to 490px and heading to 30px; reference uses about 600px and 46px. Restore reference header, left headline and form proportions with scoped CSS.
- Preserve recent auth setup eligibility logic, conditional account link labels, validation, remember-me default, notices and sign-up page. Keep Google option removed. No backend, route or auth behavior changes.
- Desktop acceptance: header 80px; 600px card near x1164/y203; 60px inputs and CTA; left two-line headline near x83/y858. Reserve card height when setup status hides the footer, without introducing an unauthorized account link. Allow validation expansion naturally.
- Mobile: form first, 16px inputs, 44px touch controls, stable scrollbar spacing, narrow-screen wrapping and normal vertical scrolling.
- Direct implementation/review only. Verify desktop/mobile/laptop geometry, keyboard/password/error states, relevant tests, typecheck/lint/build, contrast and screenshots. Preserve unrelated edits and leave changes uncommitted.
