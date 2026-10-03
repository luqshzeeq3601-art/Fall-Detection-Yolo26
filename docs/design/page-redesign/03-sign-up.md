# 03 — Sign-up page (`/signup`)

## 1. Purpose and source paths

- Purpose: create a local operator account, collect the minimum role/care context, and enter the authenticated workspace after a successful request.
- Current sources: [`frontend/src/pages/SignUpPage.tsx`](../../../frontend/src/pages/SignUpPage.tsx), [`frontend/src/features/auth/SignUpAccountStep.tsx`](../../../frontend/src/features/auth/SignUpAccountStep.tsx), [`frontend/src/features/auth/SignUpCareStep.tsx`](../../../frontend/src/features/auth/SignUpCareStep.tsx), [`frontend/src/features/auth/authValidation.ts`](../../../frontend/src/features/auth/authValidation.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), [`src/eldercare/api/routers/auth.py`](../../../src/eldercare/api/routers/auth.py), and [`frontend/src/assets/signup-art.png`](../../../frontend/src/assets/signup-art.png).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: one form containing account fields, password strength, confirm password, caregiver/facility-admin role, optional home/facility choice and name, terms acceptance, and account creation.
- `code-present (runtime unverified)`: API payload maps to `full_name`, `email`, `password`, `organization`, `care_setting`, and `job_role`; successful sign-up sets the user and navigates to `/app`.
- `code-present (runtime unverified)`: backend validates password/email, rejects duplicate email with 409, and makes the first account an admin.
- `demo/mock`: local sign-up artwork and fixture/test transport are synthetic; they do not create a real account.
- `partial`: components are named account/care “steps” but the current page renders both sections in one long form; there is no step progress or back/next state.
- `absent`: invitation workflow, email verification, organization management, and role administration are not present.

## 3. Proposed hierarchy

1. Public header with mark and Back to home.
2. Compact progress marker: `1 Account` and `2 Care setting`, clearly labelled as one reviewable form if no staged submit is implemented.
3. Account panel: name, email, password, confirm, role cards, terms.
4. Care-context panel: optional home/facility and name, with why it appears explained in one line.
5. Submit row: Create account plus an existing-account link.
6. Side artwork is synthetic and secondary; the form remains the task anchor.

## 4. Desktop and mobile wireframe

```text
1440 × 1000
[mark]                                                       [Back to home]
┌──────────────────────────────┬─────────────────────────────────────────────┐
│ synthetic camera/pose art    │ Create your account                         │
│ three short capability notes │ [1 Account]──[2 Care setting]               │
│                              │ Name · Email · Password · Confirm            │
│                              │ [Caregiver] [Facility admin]                 │
│                              │ [ ] Terms and Privacy                        │
│                              │ Optional care setting + name                 │
│                              │ [              Create account              ]  │
│                              │ Already have an account? Sign in             │
└──────────────────────────────┴─────────────────────────────────────────────┘

390 × 844
[mark] [Back]
Create your account
[Account fields]
[role cards stacked]
[terms]
[Care setting optional]
[Create account]
Already have an account? Sign in
```

## 5. Controls and states

- Controls: text fields, password toggles, role radios, optional care-setting radios, terms/privacy notices, Create account, Sign in, home link.
- Loading: disable all submit-affecting controls and use `Creating account…`; preserve values so a transient request failure is recoverable.
- Validation: field errors cover missing name/email, password rules, mismatch, missing role, and terms; focus the first invalid field and keep optional care fields optional.
- Duplicate email: attach the backend 409 message to Email and invite Sign in; do not clear the entire form.
- Sign-up disabled/server/network error: show a direct alert with retry guidance; do not imply account creation.
- Signed-in state: show the existing account notice and dashboard link; creating another account remains an explicit action.
- Terms/privacy notices are informational until a real legal document source exists.

## 6. Responsive and accessibility rules

- At 390px, keep the form in a single column and place artwork after submit; role/care choices remain large radio targets.
- Use fieldsets/legends for role and care setting, real labels, `aria-invalid` and descriptions, one `h1`, and an alert live region.
- Do not rely on the three-step marker alone; announce the current section in text. Preserve keyboard order from name to submit.
- The password strength indicator is supplementary text, never the only validation signal.

## 7. Synthetic image prompt

```text
Design a synthetic sign-up page reference for ElderCare Vision, a local fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable form panels, and restrained cobalt/mint glass accents only in synthetic public artwork. Show Create your account, account fields, password strength, role radio cards for Caregiver and Facility admin, optional Home/Facility context, terms acceptance, Create account, and Sign in link. Desktop 1440x1000 uses a two-column layout; mobile 390x844 stacks the form and keeps the submit action visible. No real people, patient data, credentials, medical guarantees, fabricated metrics, deployment dashboard, or code.
```
