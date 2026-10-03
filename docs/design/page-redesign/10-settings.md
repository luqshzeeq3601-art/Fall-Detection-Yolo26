# 10 — Settings page (`/app/settings`)

## 1. Purpose and source paths

- Purpose: manage supported detection/display/alert/data preferences, cameras, and the signed-in operator account with clear save scope and effective-time behavior.
- Current sources: [`frontend/src/pages/SettingsPage.tsx`](../../../frontend/src/pages/SettingsPage.tsx), [`frontend/src/features/settings/useWorkspaceSettings.ts`](../../../frontend/src/features/settings/useWorkspaceSettings.ts), [`frontend/src/api/platform.ts`](../../../frontend/src/api/platform.ts), [`src/eldercare/api/routers/settings.py`](../../../src/eldercare/api/routers/settings.py), [`src/eldercare/api/routers/cameras.py`](../../../src/eldercare/api/routers/cameras.py), [`src/eldercare/api/routers/auth.py`](../../../src/eldercare/api/routers/auth.py), and [`src/eldercare/incidents/retention.py`](../../../src/eldercare/incidents/retention.py).

## 2. Current functionality and boundaries

- `code-present (runtime unverified)`: Detection tab with calibrated defaults/threshold and minimum-down overrides, skeleton/box/head-blur toggles; Alerts tab with browser notification/sound; Data & privacy retention and reviewed JSONL export; Cameras tab rename/enable/delete; Account tab identity, password change, and team listing.
- `code-present (runtime unverified)`: settings are fetched/saved through `/settings`; backend applies detection/overlay changes on the next source start and restricts workspace writes to admins when a user is present.
- `code-present (runtime unverified)`: camera deletion is blocked when incidents reference it; disabling remains available. Notification permission is browser-controlled.
- `partial`: team-list failures are swallowed in the current Account tab; redesign should expose unavailable data and retry. Retention changes can permanently delete old incidents/keyframes and need a clear pre-save warning.
- `absent`: RTSP add/test, provider/key entry, team invites, role editor, SMS/phone/emergency settings, and VLM configuration are not current features; do not add them from historical mockups.

## 3. Proposed hierarchy

1. Header: Settings, one-line scope, saved/unsaved indicator.
2. Persistent settings navigation: Detection, Alerts, Cameras, Data & privacy, Account, with URL `?tab=` preserved.
3. Panel body: one concern per section, plain explanation, control, current value, and effective-time note.
4. Save bar for server-persisted tabs: `All changes saved`, Discard, Save changes; immediate camera/account actions use their own confirmation/result.
5. Danger/permission copy: retention deletion, camera delete restrictions, browser notification support, and admin-only operations.

## 4. Desktop and mobile wireframe

```text
1440 × 1000  [232 sidebar] [72 topbar]
┌──────────────────────────────────────────────────────────────────────────────┐
│ Settings                         [All changes saved]                          │
│ ┌──────────────────────┐ ┌──────────────────────────────────────────────────┐ │
│ │ Detection             │ │ Detection                                         │ │
│ │ Alerts                │ │ calibrated default toggle + threshold sliders    │ │
│ │ Cameras              │ │ overlay toggles + “next source start”             │ │
│ │ Data & privacy        │ │                                                  │ │
│ │ Account               │ │ [Discard] [Save changes]                          │ │
│ └──────────────────────┘ └──────────────────────────────────────────────────┘ │

390 × 844
[menu] Settings [saved state]
[section selector / horizontal tabs]
[active section card]
[effective-time or destructive warning]
[Discard] [Save changes]
```

## 5. Controls and states

- Controls: tabs, calibrated-default switch, two sliders, overlay switches, notification/sound switches, test notification, retention select, export, camera enable/rename/delete, password form, team list, Save/Discard.
- Loading: show `Loading settings…`, camera list loading, and account/team loading per section; do not render false defaults as saved values.
- Dirty: show `You have unsaved changes`; Discard restores server state; Save changes remains disabled until dirty and reports only after a successful response.
- Error: preserve draft values and show the API message; provide Retry for reads. Admin 403 is an explicit permission message, not a generic failure.
- Retention: before saving a finite retention period, state that older incidents and keyframes will be permanently deleted by the hourly policy; require an explicit confirmation step in the proposed flow.
- Cameras: disabled/online/degraded/offline and last health are factual; delete conflict points to Disable instead. Account/team failure gets a retry and does not disappear.
- Unsupported: no RTSP/provider fields; show a small `Not available in this workspace` note only when a user asks for that future capability.

## 6. Responsive and accessibility rules

- At 390px, make section navigation a labelled horizontal tab list or select, keep save bar sticky but non-obscuring, and stack forms.
- Every switch has a visible label and detail; sliders expose value and endpoint meaning; destructive actions require text confirmation.
- Use fieldsets/legends, semantic `nav`, `aria-current` for tabs, `role="status"` for save messages, and `role="alert"` for failed writes.
- Do not put credentials, RTSP URLs, or provider secrets in the design or image prompt.

## 7. Synthetic image prompt

```text
Design a synthetic authenticated Settings page for ElderCare Vision, a local temporal fall-detection research prototype. Use cool clinical daylight. Exact palette: canvas #F3F7FA, surface #FFFFFF, text #142B3C, muted #526675, border #D7E3EA, primary cobalt #245DDA, mint #DDF3EE with dark teal #126B5A, amber #8A5A00 on #FFF1D6, red #B42332 on #FDECEF. Use Sora headings (proposed), existing locally bundled Plus Jakarta Sans body, proposed IBM Plex Mono for IDs/units. Use 8px spacing, 16px cards, 10px controls, subtle shadows, solid readable panels, no 3D art or unsupported RTSP/provider tabs. Show desktop 232px sidebar + 72px top bar, Settings navigation with Detection, Alerts, Cameras, Data & privacy, Account, supported switches/sliders/forms, saved/unsaved save bar, effective-next-source note, and a clear retention deletion warning. Adapt to mobile 390x844 with stacked sections and sticky accessible save actions. Use synthetic illustrative data only, no credentials, patient data, emergency settings, fabricated metrics, or code.
```
