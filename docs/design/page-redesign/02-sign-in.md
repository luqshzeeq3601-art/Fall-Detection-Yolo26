# 02 — Sign-in page (`/signin`)

## 1. Purpose and source paths

- Purpose: let an existing operator authenticate without confusion, then return to the requested `/app` location or the dashboard.
- Current sources: [`frontend/src/pages/SignInPage.tsx`](../../../frontend/src/pages/SignInPage.tsx), [`frontend/src/pages/AuthPages.css`](../../../frontend/src/pages/AuthPages.css), [`frontend/src/features/auth/AuthField.tsx`](../../../frontend/src/features/auth/AuthField.tsx), [`frontend/src/features/auth/authValidation.ts`](../../../frontend/src/features/auth/authValidation.ts), [`frontend/src/features/auth/AuthNotice.tsx`](../../../frontend/src/features/auth/AuthNotice.tsx), [`frontend/src/features/auth/AuthProvider.tsx`](../../../frontend/src/features/auth/AuthProvider.tsx), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), and [`src/eldercare/api/routers/auth.py`](../../../src/eldercare/api/routers/auth.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: email/password validation, password visibility toggle, remember-me flag, sign-in request, password clearing on failure, and safe `/app`-prefixed `next` navigation.
- `code-present (runtime unverified)`: API errors distinguish server rejection from network unavailability; 401 handling is session-aware in `AuthProvider`.
- `demo/mock`: when `VITE_USE_MOCK=true`, `AuthProvider` preloads a fixture operator, but `authApi.login` and `authApi.signup` still use HTTP unless tests inject a client; the flag is not an offline-isolated account transport.
- `partial`: the current privacy note says video stays on-device without explaining that an optional configured VLM may receive incident evidence images, uploaded videos are stored on the configured server, and `Record 10 s` is a manual browser download.
- `code-present (runtime unverified)`: backend creates a session cookie, rate-limits failed attempts, and validates credentials in `auth.py`.
- `partial`: Forgot password opens an informational notice; no password-reset endpoint or recovery flow exists.
- `absent`: SSO, MFA, account recovery email, and credential persistence in the frontend are not present.

## 3. Proposed hierarchy

1. Public header with mark and a small `Back to home` link.
2. Left proof panel: one short sentence about local video processing, a synthetic abstract camera/evidence motif, and the research-POC boundary.
3. Right sign-in panel: `Welcome back`, email, password, remember me, forgot-password notice, primary Sign in, create-account link.
4. Keep terms/privacy links secondary and below the task.

## 4. Desktop and mobile wireframe

```text
1440 × 1000
[mark]                                                       [Back to home]
┌───────────────────────────────┬────────────────────────────────────────────┐
│ synthetic local-evidence art  │ Welcome back                               │
│ “Inference runs locally.”     │ [Email____________________________]         │
│ prototype boundary            │ [Password________________________] [show]  │
│                               │ [ ] Remember me       Forgot password?      │
│                               │ [                 Sign in                 ]  │
│                               │ New here? Create an account · Terms · ...   │
└───────────────────────────────┴────────────────────────────────────────────┘

390 × 844
[mark]                                      [Back to home]
[Welcome back]
[Email]
[Password + show]
[Remember me] [Forgot password?]
[Sign in]
New here? Create an account
[compact synthetic boundary card]
```

## 5. Controls and states

- Controls: email, password, visibility toggle, remember checkbox, Sign in, create-account link, home link, informational notice buttons.
- Loading: disable the form and change the action to `Signing in…`; retain entered email and clear only the password after a rejected request.
- Validation: show field-specific messages after submit and restore focus/reading order to the first invalid field.
- 401/429/server error: show the API message in an alert, explain retry timing for rate limiting when supplied, and keep the form usable after the request settles.
- Network error: say the API could not be reached and point to the local server; do not expose stack traces.
- Signed-in state: show the existing email with an `Open the dashboard` path, while preserving the form only if the user deliberately chooses it.
- Forgot password: clearly mark the current notice as unavailable rather than implying an email was sent.
- Privacy note: use precise local-inference language and link to the configured evidence-sharing/storage explanation; do not promise that every video frame stays on-device.

## 6. Responsive and accessibility rules

- At 390px, render the form first and move artwork below it; keep the submit button in the first viewport.
- Use a labelled `main`, one `h1`, real labels, `aria-invalid`, `aria-describedby`, `role="alert"` for errors, and a live region for submission status.
- Visibility toggles are named buttons; the password remains masked by default. Do not reveal or log credentials in artwork or screenshots.
- Preserve visible focus and 44px controls; the notice dialog traps focus and returns it to the trigger.

## 7. Synthetic image prompt

```text
Design a synthetic sign-in page reference for ElderCare Vision, a local fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed, add later as a local licensed asset with no external fetch), existing locally bundled Plus Jakarta Sans body at 15/24, proposed IBM Plex Mono for IDs/units at 12/18. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid white form panels, and restrained cobalt/mint glass accents only in a synthetic public artwork panel. Show “Welcome back”, labelled email and password fields, a masked-password visibility control, remember me, unavailable-for-now forgot-password notice, Sign in, create-account link, and precise privacy copy: inference runs locally, optional configured VLM enrichment may share incident evidence images, uploaded videos stay on the configured server, and browser recording is manual. Desktop 1440x1000 uses a two-column public layout; mobile 390x844 puts the form first and stacks the synthetic artwork below. No real people, patient data, credentials, medical guarantees, operational metrics, decorative dashboard, or code.
```
