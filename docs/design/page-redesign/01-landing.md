# 01 — Landing page (`/`)

## 1. Purpose and source paths

- Purpose: give a care operator or project reviewer one clear reason to try the research prototype, explain the local temporal-detection workflow, and route to sign in or account creation.
- Current sources: [`frontend/src/pages/LandingPage.tsx`](../../../frontend/src/pages/LandingPage.tsx), [`frontend/src/pages/LandingPage.css`](../../../frontend/src/pages/LandingPage.css), [`frontend/src/api/benchmarkData.ts`](../../../frontend/src/api/benchmarkData.ts), [`frontend/src/features/auth/AuthProvider.tsx`](../../../frontend/src/features/auth/AuthProvider.tsx), and [`frontend/src/assets/hero-art.png`](../../../frontend/src/assets/hero-art.png).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: header navigation to How it works, Results, Privacy, sign-in, sign-up, and an auth-aware dashboard CTA.
- `code-present (runtime unverified)`: explains the camera → pose/temporal detector → alert/review sequence and a local-inference privacy boundary in page copy.
- `code-present (runtime unverified)`: shows the frozen benchmark snapshot from `BENCHMARK` (59/60 recall, 59/(59+2) event precision, p95 1.58 s) with a false-alarm qualification link.
- `demo/mock`: `hero-art.png` is local illustrative artwork; it is not a camera capture or deployment proof.
- `partial`: results are a static artifact snapshot; there is no public metrics API, experiment selector, or live status check on this route. The current privacy copy overstates the boundary: configured VLM enrichment may send incident evidence images, uploaded videos are stored on the configured server, and browser recording is a manual download.
- `absent`: contact/demo booking, password/session management, and real-time camera preview are outside the public route.

## 3. Proposed hierarchy

1. Compact public header: mark, three anchor links, Sign in, and one cobalt `Create an account` action.
2. Hero thesis: “See the evidence between camera and caregiver” with a short research-prototype qualifier and one synthetic evidence contact strip as artwork.
3. Proof row: three measured values with source labels and a visible “held-out false-alarm duration is limited” note.
4. Three-step workflow: capture, temporal confirmation, human review.
5. Privacy boundary: local inference, incident evidence retention, optional configured evidence sharing, and human review.
6. Final CTA and footer: route to sign-up and retain the safety boundary.

## 4. Desktop and mobile wireframe

```text
1440 × 1000
[mark] [How it works] [Results] [Privacy]                 [Sign in] [Create account]
┌──────────────────────────────────────────────────────────────────────────────┐
│ SEE THE EVIDENCE BETWEEN CAMERA AND CAREGIVER   [synthetic contact strip]    │
│ short prototype boundary + [Create account] [See measured results]           │
└──────────────────────────────────────────────────────────────────────────────┘
[59/60 event recall] [59/(59+2) precision] [1.58 s p95] [qualification note]
[01 Capture]                [02 Confirm]                 [03 Review]
[local inference] [incident evidence] [human review]              [Get started]

390 × 844
[mark]                                               [menu]
SEE THE EVIDENCE BETWEEN CAMERA AND CAREGIVER
[contact strip, synthetic] [Create account]
[measured result cards stacked]
[Capture → Confirm → Review]
[privacy boundary] [Sign in]
```

## 5. Controls and states

- Controls: anchor links, Sign in, Create an account, Open dashboard when already signed in, and full-report link.
- Signed-in state: replace duplicate auth actions with `Open dashboard`; do not imply a new session was created.
- Artwork load failure: preserve the hero copy and show a labelled neutral placeholder; never hide the CTA.
- Benchmark unavailable or stale: show `Evaluation snapshot unavailable` with a link to the report; do not replace it with zeros.
- Privacy copy: say `Inference runs locally; optional configured VLM enrichment may share incident evidence images, and uploaded videos stay on the configured server.` Do not say every frame never leaves the host or that every alert is already confirmed by a person.
- Loading: not expected for the static route; if a future public metrics request is added, use skeleton labels and an explicit source timestamp.
- Error/empty: use plain copy and a next action; no decorative alert styling.

## 6. Responsive and accessibility rules

- At 390px, stack hero copy before artwork, keep the primary CTA in the first viewport, and make anchors a labelled menu or horizontal scroll row.
- Preserve one `h1`; use `h2` for workflow/results/privacy sections and real ordered list semantics for the three steps.
- Hero artwork is decorative (`alt=""`) when the copy carries the meaning; report links and CTAs retain visible focus.
- Result values include text units and the qualification note in the accessible name; colour never carries the metric meaning alone.
- Respect reduced motion and keep artwork static when requested.

## 7. Synthetic image prompt

```text
Design a synthetic editorial landing-page reference for ElderCare Vision, a research prototype for local temporal fall-detection evidence. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed, add later as a local licensed asset with no external fetch), existing locally bundled Plus Jakarta Sans body at 15/24, and proposed IBM Plex Mono for IDs/units at 12/18. Use 8px spacing, 16px card radius, 10px control radius, subtle shadows, solid readable panels, restrained blue/mint glass accents only in public artwork. Show a calm hero headline about seeing evidence between camera and caregiver, a clearly synthetic three-frame contact strip, three workflow steps, qualified measured-result cards, privacy copy that says inference is local while configured VLM enrichment may share incident evidence images and uploaded videos remain on the configured server, and sign-in/create-account actions. No real people, patients, faces, camera footage, fabricated metrics, medical guarantees, 3D operations dashboard, or implementation/code. Compose desktop 1440x1000 with a wide editorial hero; adapt to mobile 390x844 by stacking the hero, strip, results, and CTA with readable 44px controls.
```
