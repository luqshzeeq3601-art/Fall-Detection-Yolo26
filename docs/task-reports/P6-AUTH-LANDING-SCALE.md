# Auth sizing aligned with landing

Date: 2026-10-03. Direct coordinator implementation, verification and review. No subagents.

## Change

- Both desktop form cards reduced from 600px maximum to 460px. Sign-in's forced 700px minimum card height removed; its normal Full HD card measures about 540px tall. Signup normal Full HD card measures about 744px tall.
- Auth headers use a 64px height, 36px brand mark and 18.5px wordmark, matching the landing's nominal 64px header and brand sizes. The landing header's rendered 65px includes its bottom border. Back-to-home links now use 15px text and 20px icons.
- Desktop form headings are 30px. Sign-in fields/buttons are 48px high; signup fields/buttons 44px. Input text stays 16px, visibility buttons stay 44px. Signup feature panel is 520px wide, with 42px heading, 16px narrative and 56px icons. Signup uses the landing's 1560px content-container scale.
- Artwork, color/contrast tokens and native auth behavior retained. Signup role cards stay removed. Sign-in setup-aware links and Google removal retained. No landing source changes.

## Verification

- Typecheck PASS; repo-wide frontend lint PASS; 6 relevant test files / 27 tests PASS; production build PASS. CSS-only production edits, no new behavior tests added.
- Browser: both routes across 11 sizes each (1920x1080, 1586x992, 1366x768, 1100x820, 1000x800, 768x1024, 844x390, 430x932, 390x844, 360x800, 320x568). All 22 checks pass horizontal overflow and header/card/control bounds. Inputs 16px at all sizes; no signup role cards. Both normal Full HD pages have scroll dimensions exactly 1920x1080 and 460px form width.
- Mobile empty-submit expansion passes without horizontal overflow: five signup errors and two sign-in errors. Password visibility toggles correctly and restores masking. Existing signup-to-signin and back-to-home navigation used successfully during verification.
- Desktop and phone viewport screenshots visually inspected. Evidence: `frontend/output/playwright/auth-landing-scale/` contains signin-fullhd.jpg, signup-fullhd.jpg, signin-mobile.jpg, signup-mobile.jpg and viewports.json. These are browser viewport captures, not full-page mobile captures.
- Direct code/CSS review approved; no unresolved Critical/Important scoped finding. No independent reviewer claimed. Existing consent defaults, API payloads and role assignment are unchanged.

## Scope

Production changes only in SignInPage.css and SignUpPage.css. No new artwork, dependencies, backend/model/dataset/benchmark changes. Existing unrelated workspace work retained. No commits, push, deployment or real account creation.

Previews: http://127.0.0.1:5176/signin and http://127.0.0.1:5176/signup.
