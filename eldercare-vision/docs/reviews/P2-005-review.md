# P2-005 — Inference timing metrics: reviewer report

- Reviewer: fresh Reviewer subagent (no prior implementation/testing context), read-only review.
- Inputs read in full: `docs/task-briefs/P2-005.md`, `docs/task-reports/P2-005.md`,
  `src/eldercare/vision/pose/timing.py`, `git diff src/eldercare/vision/pose/pipeline.py`,
  `tests/unit/test_pose_timing.py`.
- Verification method (per instructions): `git diff`/`stat`/`status`, targeted greps,
  static read, `ruff check`, `ruff format --check` (3 task files), `pytest --collect-only`.
  Suite was NOT re-executed; pass counts below are tester-reported + collect-only cross-checked.
- No file was modified by this review except the creation of this review file. No commit made.

## Verdict: APPROVE

No Critical or Important findings. All AC-P2-005a..g verified PASS on static evidence.
The `round(..., 9)` reconciliation is ruled ACCEPTABLE (see Rounding ruling).
Task may complete; no fixes required.

## Findings

### Critical — none.

### Important — none.

### Minor — none.

### FYI

- FYI-1 — `tests/unit/test_pose_timing.py:6` (module docstring, prose wrap) begins a
  continuation line with the words `import ultralytics/torch/cv2`. A naive
  `^(import|from)\s+(ultralytics|torch|cv2)` grep flags this line, but it is docstring
  prose, not a code import: the real import-statement sweep (`^import …` / `^from …` as
  code) over the 3 task files shows only stdlib (`math`, `dataclasses`, `time`,
  `json`, `sys`), `numpy`, `pytest`, and first-party imports — zero framework imports.
  Evidence: full import list captured during review; `sys.modules` runtime test present
  (`test_runtime_stays_free_of_frameworks`, `tests/unit/test_pose_timing.py:593`).
  Not a violation. Suggested future grep-proofing: reword so no docstring line starts
  with `import `.
- FYI-2 — `total_ms` is computed independently as `round((t2-t0)*1000, 9)` rather than as
  `predict_ms + adapt_ms` (`src/eldercare/vision/pose/timing.py:117-120`). Exact equality
  on controlled stamps is pinned by `test_timings_from_stamps_exact_brief_vector`
  (`tests/unit/test_pose_timing.py:244-249`) and holds (10.0/15.0/25.0 are exactly
  representable). In general, `round(a)+round(b)` vs `round(a+b)` can differ by 1 ulp at
  1e-9 ms granularity — semantically nil and outside the AC, which requires equality only
  on controlled stamps. No action.
- FYI-3 — Full-repo `ruff format --check .` ("107 files already formatted") and full-suite
  `pytest` (469 passed) are tester-reported and were not re-executed per review
  instructions; spot-verified instead: `ruff check` + `ruff format --check` PASS on the
  3 task files, collect-only counts match the report exactly (75 / 53).

## Review scope checks (evidence)

1. Additive-only pipeline diff — PASS. `git diff --stat HEAD` shows exactly one modified
   file (`src/eldercare/vision/pose/pipeline.py`, +38/−1); all other changes are new files.
   Diff hunks are ONLY: (a) docstring timing paragraph, (b) `PoseTiming`/`timings_from_stamps`
   import, (c) `PosePipelineResult.timing: PoseTiming | None = None` + `TypeError` guard,
   (d) `timer: Callable[[], float] = time.perf_counter` param + callable/`TypeError` guard,
   (e) `t0`/`t1`/`t2` stamps + `timings_from_stamps` attach in `process_frame`.
   Unchanged (absent from diff): `orig_shape`/image cross-check text, `del results`
   no-retention line, identity propagation, adapter `ValueError` frame-context wrapping,
   predictor path (no try around `predict` — exceptions propagate unwrapped),
   `process_capture_read`/`process_queued_frame` (zero hunks — `None` paths create no timing),
   log record block (`pose.frame_processed`, `frame_id`, `person_count`), `__repr__`
   (`camera_id` only). Existing tests untouched: `git diff HEAD -- tests/` empty;
   `tests/unit/test_pose_pipeline.py:199` (result constructed without `timing`) unmodified
   and kept green by the `None` default.
2. Units/boundaries — PASS. `_MS_PER_SECOND = 1000.0` explicit (`timing.py:37`); ms-only
   math in `timings_from_stamps` (`timing.py:117-120`); `PoseTiming.__post_init__` validates
   every field finite and `>= 0` with naming `ValueError`, bools rejected (`timing.py:41-48,
   77-80`); zero allowed (`0.0` exact, test at `test_pose_timing.py:252`); backwards
   (`t1 < t0`, `t2 < t1`) and non-finite stamps fail closed with naming `ValueError`
   (`timing.py:104-116`); `None`/failure paths fabricate nothing (timer-consumption contract
   3/1/2/0 calls pinned by tests at `test_pose_timing.py:409-455`); only predict+adapt are
   stamped — no capture/queue latency.
3. Clocks — PASS. `timer` default is the `time.perf_counter` function object, not a call
   (`pipeline.py:181`; runtime-confirmed defaults `(monotonic, perf_counter)`); `clock`
   default `time.monotonic` preserved (`pipeline.py:180`); independent injection both
   directions pinned (`test_advancing_clock_alone_leaves_timing_unchanged`,
   `test_advancing_timer_alone_leaves_observation_unchanged`); non-callable `timer` →
   `TypeError` (`pipeline.py:190-191`, test at `test_pose_timing.py:559`); zero sleeps —
   `rg -n "sleep"` over the 3 task files has no hits; all durations from programmed
   `FakeTimer` sequences.
4. Rounding — PASS, ACCEPTABLE (see ruling). Ordering checked on raw stamps BEFORE
   `round(..., 9)` (`timing.py:107-120`).
5. Security/scope — PASS. No `ultralytics`/`torch`/`cv2` code imports in task files
   (only pre-existing lazy `from ultralytics import YOLO` in `inference.py:86`, untouched,
   never executed by CPU tests); `rg -in "benchmark|FPS|RTX|3070|ByteTrack|onnx|tensorrt|
   mqtt|postgres|prometheus|OpenTelemetry|frontend|tracking|temporal|fall|dataset"` over the
   3 task files has no hits; no hardware numbers anywhere; `pyproject.toml` untouched
   (`git diff HEAD -- pyproject.toml` empty); secret sweep
   (`api_key|password|secret|PRIVATE|rtsp://.*:.*@`) over task files + report has no hits;
   no Phase 3 systems.
6. Test quality — PASS. 75 tests collected, matching the report; every AC area pinned with
   CPU-only fakes + programmed timers (validation per field, exact brief vector
   `100.0/100.010/100.025 → 10.0/15.0/25.0`, zero-duration, stage separation, backwards +
   non-finite + bool rejection, 0/1/3-person integration, missing-keypoint passthrough,
   fresh-timings/no-state-growth with `_TIMING_VARS` exact-match, failure-path timer
   consumption, clock/timer independence, default-vs-fake contract identity, log-shape and
   repr regression, `sys.modules` freedom with pure-list stubs, ms-vs-seconds unit test,
   P2-004 fake-capture fan-in preservation). Regression files genuinely unmodified
   (absent from diff) and collect to exactly 50 unit + 3 integration = 53.

## AC verdicts

- AC-P2-005a (exact timings 0/1/3 persons, `total == predict + adapt`): PASS.
- AC-P2-005b (zero allowed; finite non-negative; ms units): PASS.
- AC-P2-005c (injectable timer; clock/timer independence; `TypeError`; no sleeps): PASS.
- AC-P2-005d (no fabrication; fail-closed anomalies): PASS.
- AC-P2-005e (no pose-contract regression; log/`__repr__` unchanged): PASS.
- AC-P2-005f (framework freedom; predict/adapt stamping only; no out-of-scope claims): PASS.
- AC-P2-005g (`ruff check` + `ruff format --check` + `pytest` green, no new deps): PASS
  (tester-reported full gates; reviewer spot-verified task files + collect-only counts).

## Scope/secret verdicts

- Forbidden scope: CLEAN (no benchmark/FPS/RTX/hardware numbers; no
  ByteTrack/temporal/fall/dataset/ONNX/TRT/MQTT/DB/Prometheus/frontend/Phase 3 code;
  no capture/queue latency in metrics; `pyproject.toml` untouched; existing tests and
  `tests/integration/*` unmodified).
- Secrets: CLEAN (no credentials, keys, or connection strings in task files or report).

## Rounding ruling: ACCEPTABLE

The brief's prescribed vector (`t = [100.0, 100.010, 100.025]` → exactly `10.0/15.0/25.0`)
is unsatisfiable with pure `(t1-t0)*1000.0` because the raw product is `10.000000000005116`
(reproduced during review). The implementation normalizes with `round(..., 9)` (`timing.py:38,
117-120`), discarding only ~1e-12 s (sub-picosecond) dust far below any real clock resolution
(`time.perf_counter` granularity is nanoseconds at best). Ordering is validated on the RAW
stamps before rounding, so a backwards clock can never be rounded into hiding, and
zero-duration stamps still yield true `0.0`. The reconciliation is fully disclosed in the
module docstring (`timing.py:16-23`) and the implementer report (§7/A1, §8). No hidden
behavior. No change requested.

## Counts

- Focused (new `tests/unit/test_pose_timing.py`): 75 collected — matches reported 75 passed.
- Regression (`tests/unit/test_pose_pipeline.py` + `tests/integration/test_pose_pipeline.py`,
  unmodified): 53 collected (50 + 3) — matches reported 53 passed.
- Full suite: 469 passed tester-reported (= 394 prior + 75 new) — not re-executed per review
  instructions; collect-only counts reconcile exactly.
- Ruff: `ruff check` + `ruff format --check` PASS on the 3 task files (reviewer-executed);
  full-repo gates tester-reported green.
- Findings: 0 Critical, 0 Important, 0 Minor, 3 FYI.
