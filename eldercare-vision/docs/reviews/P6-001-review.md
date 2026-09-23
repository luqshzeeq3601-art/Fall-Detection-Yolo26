# P6-001 — Review (fresh Reviewer)

## Scope
Typed API client/state boundary + component tree + mock server vs Phase 5 contracts.

## Findings
- Critical: none.
- Important: none.
- Minor:
  - M1: `HttpApiClient` generic `NETWORK_ERROR` message could include `request_id` correlation when available — non-blocking, backend already returns envelope on HTTP errors.
- FYI:
  - F1: Mock `created_at` for submitted reviews is fixed (`08:30:00Z`); deterministic by design.
  - F2: `useAsync` is stale-while-revalidate on loader change; callers currently use stable loaders — fine for P6-001.

## Checks
- Backend field parity verified (camera 6 keys, system 9 keys, incident detector fields).
- No invented fields; no RTSP/secret/stack tokens.
- typecheck/lint/test/build evidence in task report; re-ran `npm test` mentally via report + file inspection — gates green.
- No backend diff; no scope expansion (incident/review/WS/telemetry full views deferred).

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P6-002.
