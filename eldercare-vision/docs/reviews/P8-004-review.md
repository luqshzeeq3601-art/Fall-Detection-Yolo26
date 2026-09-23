# P8-004 — Review (fresh Reviewer, PERF+OPS lens)

## Scope
Soak/resource test vs FAILURE_TESTS.md FT-12/FT-09, UAT-20, and the P8-004 brief.

## Findings
- Critical: none.
- Important: none.
- Minor: none.
- FYI:
  - F1: Workload duration is CI-scale (2,000 frames / ~2 s compute), specified
    in the brief because no authoritative duration exists — the report labels
    it as such; multi-hour longevity stays deployment-time validation.
  - F2: tracemalloc start reads 0 B (tracing began at loop start); the honest
    signal is peak ≈ end (2.57 ≈ 2.54 MB): flat, no growth trend.
  - F3: VRAM trend is N/A in CI (no accelerator); target-PC measurement
    belongs to Phase 9 benchmarking on the RTX 3070 host.

## Checks
- Trend numbers in the report match the observed probe (elapsed, bounds,
  memory, delivery split); soak green; full 934 green; ruff/format clean.

## Verdict
**APPROVE** — 0 Critical, 0 Important. Proceed to P8-005.
