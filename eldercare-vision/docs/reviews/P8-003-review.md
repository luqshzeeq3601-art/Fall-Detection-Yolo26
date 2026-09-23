# P8-003 — Review (fresh Reviewer, security lens)

## Scope
Security/privacy audit vs CONSTRAINTS.md §9, the goal intersections, and the
P8-003 brief — including the SEC-001/SEC-002 fix loop.

## Findings
- Critical: 0.
- Important: 2 found (SEC-001 unbounded payload recursion; SEC-002 JSON
  scanner recursion) — BOTH FIXED in-task with regression tests, re-tested
  green, publisher suite unbroken. 0 remain open.
- Minor: none.
- FYI:
  - F1: Depth cap (32) and list-scan are hardening, not contract changes;
    legal payloads (flat, ≤3 levels) are byte-identical in behavior.
  - F2: The tracked-source scan is placeholder-aware by design; genuinely new
    credential patterns (non-placeholder userinfo/keys) still fail the build.
  - F3: WS binary-frame safety rests on the endpoint's broad-except prune
    (read confirmed) plus the new drill — no endpoint change needed.

## Checks
- Fixes read on disk (`publisher.py` cap + list scan, `envelope.py` catch);
  17 drills green; full 933 green; ruff/format clean; no leaks in sweep.
- Fix loop protocol honored: find → fix → independent retest (45/45 incl.
  publisher regressions) → this re-review.

## Verdict
**APPROVE** — 0 Critical, 0 Important open. Proceed to P8-004.
