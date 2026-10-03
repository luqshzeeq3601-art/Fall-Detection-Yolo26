# P6-REDESIGN-PAGES — Routed page groups

## Purpose
Complete the approved ten-route redesign after the Overview visual checkpoint. Parent brief P6-REDESIGN.md and FRONTEND_PROMPT.md remain binding.

## Scoped workers and interfaces
- Public/auth specialist: LandingPage, SignInPage, SignUpPage, public/auth CSS, validation helpers/tests. Shared Brand, NoticeDialog, Ui and generated asset imports. Auth is UI-only, routes /app, no credentials/session storage.
- Operations specialist: SurveillancePage, IncidentsPage, ReviewQueuePage and feature CSS/logic/tests; restyle CameraCard, IncidentList/Filters/Detail, EvidenceView, ReviewForm while retaining standalone tests/interfaces. Consume shared context, API client and existing hooks. Real reviews append; Skip is local; dataset actions demo-only; errors do not advance queue.
- Settings specialist: SettingsPage and section components/CSS/tests. Draft/session-only mock settings, meaningful controls, labels for unavailable API operations, no RTSP/secrets, no runtime changes. Read camera health from context.
- Coordinator: BenchmarksPage, TelemetryPage, route integration, artwork, browser QA and status/report documentation.

## Acceptance
Match page-specific supplied images, clinical glass tokens, all data provenance rules, native keyboard-accessible controls, loading/empty/error states, no sourcefile over300lines, 1440/375 visual comparison, responsive760/1024 behavior per parent. No unsupported live control silently succeeds. Browser URLs/filters remain shareable. Only router and icon dependencies.

## Verification
Focused logic/behavior tests first, typecheck/lint/build and whole suite after integration. Fresh reviewer per group and final branch review; no unresolved Critical/Important issues. No commits or backend/model/data changes.
