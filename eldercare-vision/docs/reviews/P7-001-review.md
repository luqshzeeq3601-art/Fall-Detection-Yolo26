# P7-001 — Review (fresh Reviewer)

## Scope
Mosquitto broker config + compose wiring vs ARCHITECTURE.md §3/§8,
EVENT_SCHEMA.md §4, CONSTRAINTS.md, and the P7-001 brief.

## Findings
- Critical: none.
- Important: none.
- Minor:
  - M1: Broker authentication remains anonymous-local (documented dev-only
    deviation). Acceptable: no MQTT credentials exist in any authoritative
    spec; production hardening path is written into the conf itself.
- FYI:
  - F1: `max_connections 50` / `max_queued_messages 1000` are engineering
    defaults for the single-site POC, not measured capacity figures.
  - F2: Live `docker compose up` of the broker was not executed here (config
    render validated; daemon run belongs to integration evidence if a later
    task requires it).

## Checks
- Directive values verified against files on disk; compose diff is additive
  (mount + healthcheck + comment); no settings/backend/frontend changes.
- Gates evidence in task report; full suite 830 green; ruff/format clean.

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P7-002.
