# P7-003 — Review (fresh Reviewer)

## Scope
FPS/latency/queue/reconnect metrics vs CONSTRAINTS.md §11, existing P1-006 /
P2-005 ownership contracts, and the P7-003 brief.

## Findings
- Critical: none.
- Important: none.
- Minor: none.
- FYI:
  - F1: `collect_pipeline_metrics` duck-types its sources (documented):
    a source lacking `to_dict`/attributes degrades to unknown rather than
    raising — correct for telemetry, callers must not mistake unknown for zero.
  - F2: Snapshot cadence/retention policy belongs to the service layer
    (future wiring), not this module.

## Checks
- No invented values: every field traces to `CaptureSnapshot`/`PoseTiming`
  semantics; `None` paths test-proven; producer modules untouched.
- Gates evidence in task report; full suite 866 green; ruff/format clean.

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P7-004.
