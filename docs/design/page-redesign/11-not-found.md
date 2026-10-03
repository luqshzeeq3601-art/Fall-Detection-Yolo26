# 11 — Not-found view (unmatched paths)

## 1. Purpose and source paths

- Purpose: recover from an unknown public or authenticated URL with a useful destination and enough context to tell the user where they are.
- Current source: [`frontend/src/App.tsx`](../../../frontend/src/App.tsx), where `NotFoundPage` renders `Page not found`, a short message, and a Return to home link both outside and inside the authenticated route tree.

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: catch-all route and Return to home link.
- `partial`: the current view is the same for a public typo and an authenticated `/app/*` typo; it does not offer dashboard recovery or preserve the shell context intentionally.
- `demo/mock`: none required; the text is static.
- `absent`: route suggestions, search, incident-ID recovery, and server-side redirect diagnostics are not present.

## 3. Proposed hierarchy

1. Preserve the surrounding shell when the path begins `/app`; use the public header otherwise.
2. Show a calm `Page not found` heading, the requested path in IBM Plex Mono, and one sentence explaining that no route matched.
3. Public recovery: Back to home and Sign in.
4. Authenticated recovery: Overview, Live monitor, Incidents, and a search field.
5. Keep the panel compact; no illustration is necessary beyond a small synthetic route marker.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  authenticated
[232 sidebar] [72 topbar]
                    ┌──────────────────────────────────┐
                    │ Page not found                  │
                    │ /app/unknown                     │
                    │ No route matched this address.   │
                    │ [Overview] [Incidents] [Search]  │
                    └──────────────────────────────────┘

390 × 844
[menu/topbar]
[Page not found]
[/unknown]
[Overview]
[Back to home / Sign in]
```

## 5. Controls and states

- Controls: context-aware recovery links, optional incident search, shell navigation.
- Loading: none for static recovery; if route suggestions become fetched, use a short loading message.
- Error: if recovery navigation fails, preserve the links and show the destination error inline; never loop redirects.
- Empty: not applicable; the unmatched path itself is the empty route state.
- Status: do not present the view as a backend outage unless an actual health request failed.

## 6. Responsive and accessibility rules

- At 390px, center the compact panel with 24px gutters and keep the first recovery action visible.
- Use one `h1`, a `main` landmark, a labelled path, and visible focus. Link names must describe destinations.
- Use `aria-live` only for a real navigation error; static not-found copy does not need repeated announcements.

## 7. Synthetic image prompt

```text
Design a synthetic calm not-found view for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for the requested path and units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no decorative artwork or charts. Show “Page not found”, a synthetic path like /app/unknown, a concise recovery message, and context-aware Overview, Incidents, Search, Back to home, or Sign in links. Desktop 1440x1000 uses the authenticated 232px sidebar + 72px top bar when appropriate; mobile 390x844 centers the panel with large readable controls. No real people, patient data, metrics, medical claims, or code.
```
