# P7-005 — Review (fresh Reviewer)

## Scope
Broker outage/recovery vs ARCHITECTURE.md §7, P7-002 failure semantics, and
the P7-005 brief. Security lens: no unbounded reconnect, no queue growth,
no sensitive data, core detector independent.

## Findings
- Critical: none.
- Important: none.
- Minor: none.
- FYI:
  - F1: `connect_with_retry` returns `False` for `max_attempts=0` without
    touching the transport (zero-budget policy) — consistent, documented by test.
  - F2: Live-broker outage evidence (daemon `up` + kill + recover) is out of
    unit-CI scope by design; fake-transport drills + P7-001 compose render
    stand as the reproducible evidence.
  - F3: Consumer-side dedupe on redelivered QoS-1 ids belongs to future
    bridge consumers; publisher side guarantees stable ids (test-proven).

## Checks
- Schedule math, attempt budget, shutdown, and detector-continuation probes
  verified in tests; publisher holds no queues/subscriptions (code-read
  confirmed); no secrets/RTSP in module.
- Gates evidence in task report; full suite 886 green; ruff/format clean.

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P7-006 gate.
