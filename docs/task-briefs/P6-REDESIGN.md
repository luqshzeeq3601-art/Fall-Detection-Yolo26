# P6-REDESIGN — Ten-page clinical glass frontend

## Purpose and requirements
Implement the approved FRONTEND_PROMPT.md design as a Phase 6 frontend follow-up. Ten routes, existing React19/Vite/TypeScript/plain CSS, only react-router-dom and lucide-react added. Follow supplied mockups and tokens with generated local 3D artwork; 240px sidebar, 1024px icon rail, 768px drawer.

## Interfaces
Retain typed API DTOs; separate mock-only presentation fixtures. DashboardProvider/useDashboardContext exposes cameras, system, ready AsyncState, events EventsBundle and isDemo boolean. One /app socket with idempotent reconnect/disposal/deduplication; shared camera/status queries. Extend existing needs_review query, mock date filters, descending ordering and offset pagination.

## Behavior
UI-only auth; working mock controls; unsupported live features explicitly unavailable. No credential persistence. Reviews append confirmed_fall/non_fall/uncertain; Skip never writes. Refresh same queue offset after a saved review, clamp final empty page, retain item on failed save. Dataset selection/export mock-only, latest labels, manifest schema1.0.0, exclude uncertain by default.
Use saved V6.3 results (recall59/60, precision59/61, median0.846s, p951.579s). FA/h Under evaluation; PR curve unavailable (one measured point), no fake comparisons. Current API FPS/latency are sample metrics. No live video endpoint or claimed camera safety. VLM generated context remains distinct from detector evidence; research POC boundary stays visible.

## Allowed files and workflow
frontend source/config/lockfile/assets and scoped UI task/review/progress documentation. Fresh specialists/tests/review under Superpowers; coordinator alone updates status. Sandbox denied writes to native worktree, so use the documented in-place fallback. Overview runs and is compared before remaining pages. No commits/pushes/deployment, Python/backend/model/dataset changes, secrets, sensitive media or fabricated real people/statistics.

## Acceptance
All ten pages compared at1440/375; sidebar checks768/1024; no page overflow; keyboard/focus/AA/reduced motion; loading/empty/error/disconnected states. Typecheck, lint, vitest, build pass. Cover auth/review shortcuts/queue/filtering and socket lifecycle. Replace old glass/gradient test ban with real accessibility checks without weakening DTO/security checks.

## Reports
docs/task-reports/P6-REDESIGN.md and docs/reviews/P6-REDESIGN-review.md.
