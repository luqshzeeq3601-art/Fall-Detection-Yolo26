# P6-SIGNUP-REFERENCE

- User scope: match the supplied sign-up screenshot, with readable text, Full HD desktop and mobile compatibility. Direct implementation and review; no subagents.
- Skills: frontend-design, image-to-code, design-taste-frontend, already loaded for this conversation. Existing local Plus Jakarta Sans, native CSS and Lucide components. No global router added.
- Design read: bright blue/mint caregiver signup page, one left feature panel and one right account form, camera/pose illustration between panels. Variance 3, motion 1, density 4. The reference is authoritative for composition; contrast overrides faint text.
- Image-first: generate and inspect a dedicated opaque background matching the camera, glass pose panel, interior and ribbon. Remove all UI and personal names/email. All form/headline/feature text remains real HTML.
- Reference geometry at 1586x992: header about 62px; left panel x92/y225/w560; form x949/y80/w562. Full HD may scale the feature panel/form and spacing. Form must fit normal 1920x1080 viewport; errors may grow naturally. Mobile prioritizes account form, then feature panel, with 16px inputs and 44px controls.
- Preserve current single-form signup API behavior, validation, role selection, terms opt-in, notices, password visibility, duplicate-email handling and navigation. Existing three-stage presentation strip is a visual overview, not a newly implemented wizard.
- Do not prefill reference personal details, auto-select role or accept terms. Do not submit a real account during browser testing.
- Verification: sign-up/auth regressions, frontend lint/typecheck/build, desktop/reference/laptop/tablet/mobile portrait/landscape screenshots, client-width overflow checks, password/role/notice/focus/validation checks and contrast.
- Update progress and record direct review; leave all changes uncommitted and preserve unrelated edits.
