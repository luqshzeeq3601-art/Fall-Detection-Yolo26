# P9-001 — Review (fresh Reviewer, PERF lens)

## Scope
Baseline benchmark harness vs BENCHMARK_PLAN.md §§4–6/10, AGENTS.md §8/§14,
and the task brief. Specifically hunted: benchmark contamination, incorrect
CUDA timing, warm-up leakage, unstable methodology, hidden config changes,
detector-semantic changes, accidental optimization, machine-specific hard-coding.

## Findings
- Critical: none.
- Important: none.
- Minor:
  - M1: `benchmarks/results/p9_001_baseline.json` is committed with concrete
    numbers — correct here (raw result artifact required by plan §6.10), but
    future tasks must not edit it; later variants get their own files.
- FYI:
  - F1: T201 file-waiver follows the `verify_pose_model.py` precedent with
    written justification; JSON artifact remains the machine record.
  - F2: CV 0.108 across reps reflects shared-CI-machine jitter; all three
    runs retained, none averaged away — correct handling.
  - F3: Real-model numbers still require the RTX 3070 host; the exact command
    is in the report. No claim in this task depends on them.

## Checks
- Harness read end-to-end: warmup exclusion by construction + call-count test;
  sync bracketing proven by stub-torch order test; determinism byte-proven;
  config frozen by hash test; stage mapping mirrors the P2→3 handoff fields.
- `UltralyticsPosePredictor` defaults untouched; fall config hash unchanged;
  datasets/weights untouched; git diff contains only harness/tests/artifacts/docs.
- Gates: 11/11 focused, 950 full, ruff/format clean.

## Verdict
**APPROVE** — 0 Critical, 0 Important. P9-001 complete. Do NOT start P9-002.
