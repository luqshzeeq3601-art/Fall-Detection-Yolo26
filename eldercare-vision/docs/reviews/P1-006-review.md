# P1-006 Review — Capture telemetry (fresh, read-only)

- Target: `src/eldercare/vision/stream/telemetry.py` (new, 336 lines) + `tests/unit/test_capture_telemetry.py` (new, 497 lines, 39 tests)
- Brief: `docs/task-briefs/P1-006.md` (criteria a–g + logger.py relevance rule); Spec: pack `AGENTS.md` §§9,12 + `CONSTRAINTS.md` §11 + `PRD.md` US-05
- Base: git HEAD `eef3f31`; working tree adds only the brief input, the implementer report, and the 2 target files. No tracked file modified.
- Implementer report: `docs/task-reports/P1-006.md`; tester verdict: PASS (303 tests, probes exact, logger-deferral concurred, scope clean).

## Verdict: APPROVE

No Critical or Important findings. One Minor (non-blocking doc/code precision gap in out-of-order pruning, production-unaffected). Logger deferral concurred. Scope clean.

## Re-verification (independent, not trusted from report)

| Check | Result |
|---|---|
| `python -m pytest tests/unit/test_capture_telemetry.py -q` | **39 passed in 0.29s** — matches report's 39/39 |
| `python -m pytest -q` (full suite) | **303 passed in 0.62s** — matches report (264 prior + 39 new = 303) |
| `ruff check` on both new files | **All checks passed** |
| `ruff format --check` on both new files | **2 files already formatted** |
| `git status --short` / `git diff HEAD --stat` | Only 4 untracked paths (brief input, report, `telemetry.py`, `test_capture_telemetry.py`); **zero tracked modifications** — `logger.py` untouched, no `pyproject.toml`/dep change, no forbidden-file changes |
| Real sleeps | None: no `sleep(`/`time.sleep` in either file (only `FakeSleep` double + docstrings in tests); full suite 0.62s incl. 100k-note flood + thread smoke is itself the zero-sleep proof |
| Bare `except` / `print(` / logging / backend imports in `telemetry.py` | None (grep: sole "logging" hit is a docstring sentence; imports are `math`, `threading`, `time`, `collections.deque`, `collections.abc`, `dataclasses`, `typing` + `TYPE_CHECKING`-only component hints) |
| Forbidden scope (Prometheus/OTel/MQTT/DB/hardware/dashboard/Phase-2) | None in code; module docstring lines 46–50 explicitly lists NOT-here items |

Report nit (not a finding): command-log row 5 "77 files formatted" reads as if `ruff format` rewrote 77 files; `git status` proves zero tracked modifications, so this is loose wording for a `--check` pass, not formatting churn. No action.

## 1. Honesty — CLEAN except Minor-1 (prune-hole note below)

- **None-means-unknown upheld everywhere.** `snapshot()` (`telemetry.py:279-280`): `fps = in_window / window if in_window >= 2 else None` — 0 or 1 in-window frames yield `None`, never `0.0`. Empty snapshot (`test_1`), single-frame (`test_3`), post-prune-stale (`test_10`) all pin `None`. `seconds_since_last_frame` (`telemetry.py:296`): `None` when `last_frame_at is None` — verified against `test_6b`. This deliberately diverges from `health.silence()`'s since-creation fallback (`health.py:246-257`); the divergence is documented in the report (Assumptions) and the snapshot docstring (`telemetry.py:137-138`), and it is the honest choice (no frame → unknown, not zero). Unattached components read `None`, never zero (`telemetry.py:282-292`, pinned by `test_1`).
- **Window boundary exact and consistent.** Prune (`telemetry.py:256`: `<= cutoff` popleft) and FPS count (`telemetry.py:279`: `ts > cutoff`) implement the same strict-`>` rule stated in the docstring (`telemetry.py:13-16`). Boundary pinned by `test_2b` (frame at exactly `now - window` excluded, fps 0.4 not 0.6) and `test_2c`.
- **No float-division hazard.** `_check_window` (`telemetry.py:76-89`) rejects bool/non-numeric/non-finite/`<= 0`; the window is immutable after `__init__` (single assignment, line 208), so `in_window / self._window` (line 280) cannot divide by zero and cannot yield NaN/±Inf (finite count over finite positive window). `seconds_since` is a difference of two validated finite timestamps. `note_frame(None)`/`snapshot(None)` clock values go through the same `_check_timestamp` validation (fail-fast `ValueError` on bad clocks — documented assumption, matches `health.poll` discipline). Strict-JSON safety is proven, not just argued: `allow_nan=False` round-trips on empty/populated/post-prune/capped snapshots (`test_10`, `test_10b`, `test_5`).
- **`frames_received` monotonic and honest:** incremented once per accepted note (line 260); rejected notes change nothing (pinned by `test_11b`/`test_note_frame_rejects_bool_like_health`).

## 2. Ownership — CLEAN (no finding)

- **Telemetry mutates nothing outside its deque/counter.** `telemetry.py` contains zero assignments to component state and zero calls to mutating APIs — no `.put/.get/.clear/.close`, no `notify_frame/poll`, no `attempt/stop`. Every component interaction is a read-only getter/attribute: `queue.submitted/dropped/depth` (`queue.py:56-72`, each briefly self-locked, returning ints), `health.state`/`health.last_frame_at` (`health.py:234-244`, lock-protected), `reconnect.attempts`/`consecutive_failures` (plain public attributes, `reconnect.py:182-184` — read exactly as the controller's own code reads them). Read-only proof pinned by `test_7` (state identical before/after 100 snapshots + queue contents undisturbed).
- **Lock-ordering as documented — verified by read.** `snapshot()` copies owned state under the lock and releases it (`telemetry.py:275-277`) *before* any component read (lines 282-295, with an explicit discipline comment at line 281). `note_frame()` touches owned state only and calls no component code (lines 252-260). `__repr__` follows the same discipline (owned copy lines 317-320, component reads 325-326). `clock()` is never invoked while holding the lock in any method. Single lock, no nesting, no I/O/logging/callbacks in any critical section → deadlock-free by construction. Thread smoke (`test_8`: 4 noters + 2 snapshotters, 30s join timeouts, `frames_received == 1000`) passed in this re-verification run.
- **Component getters are side-effect-free reads** (queue/health properties only take their own brief locks; reconnect reads are plain attribute loads), so no lock-order inversion is possible.

## 3. Boundedness — CLEAN except Minor-1

- **Prune rule consistent with the strict-`>` FPS rule** for the in-order (production) path: entries exactly at the cutoff are dropped by `note_frame` and would be excluded by `snapshot` alike. `snapshot()` is side-effect-free (full-scan count, no mutation — repeated snapshots identical per `test_7`).
- **MAX cap documented and honest.** `MAX_FRAME_TIMESTAMPS = 16384` with sizing rationale (`telemetry.py:68-73`: ~128 KiB, far above 1000 fps × 5 s = 5000). Cap evicts oldest-positionally (lines 258-259); under flood this *under*-reports fps (e.g. `test_5`: 100k same-ts notes → fps `16384/5.0`), i.e. it errs conservatively and never fabricates a higher rate. The stalled-clock trade-off is disclosed in the report (Limitations) and the cap path is strict-JSON-tested. With an advancing clock the window prune keeps the deque small and the cap never binds (requires >3276 fps sustained) — so the under-report regime is pathological-only. Judged documented/honest; see FYI-2.
- **Deque grows via exactly one path** (`note_frame` line 255); no other method appends. `frame_window_size` is the sole documented introspection hook (lines 229-237), as the brief permits.

## 4. Logger.py deferral — CONCUR (no finding)

`telemetry.py` performs zero logging: no logger import, no log call, no I/O of any kind (confirmed by read + grep). Both P0-006 deferred minors (raw `record.name`, unguarded `json.dumps`) therefore cannot affect any telemetry path; snapshot strict-JSON-safety is instead guaranteed by finite-float construction and proven by `allow_nan=False` round-trips. The brief's relevance rule requires a *direct telemetry requirement* plus a ≤5-line minimal diff — neither prong is met, so any `logger.py` edit would have failed the rule. `git status` confirms `logger.py` untouched. The P0-006 minors correctly stay with their owning task. Report reasoning (§logger.py decision) is accurate on all three points.

## 5. Hygiene / scope — CLEAN

- Type hints on all public APIs (incl. `LatestFrameQueue[Any] | None` generics, `Callable[[], float]` clock); frozen dataclass contract with `to_dict()` preserving `None`s (pinned by `test_1b` incl. `FrozenInstanceError`); no bare `except` (no `except` at all in `telemetry.py`; tests use only named `except BaseException as exc` for thread error capture); no `print`; stdlib-only (runtime imports are stdlib; component types are `TYPE_CHECKING`-only).
- `__repr__` carries `camera_id/frames_received/fps/depth/health` only — numerics/id/enum, URL-free by construction (holds no frames, no config URLs); credential tests (`test_9`, `test_repr_carries_ids_and_scalars_without_urls`) assert absence of user/pass/token/`rtsp://`/host/`@`. See FYI-4 for the one trust-boundary note.
- US-05 / CONSTRAINTS §11 mapping correct: report maps the capture-side subset (capture FPS → `capture_fps`; queue depth → `queue_depth`; dropped → `queue_dropped`; reconnect count → `reconnect_attempts` + consecutive `reconnect_failures`) and explicitly defers processed FPS, inference/latency, and hardware stats to later phases. Cardinality bounded by construction (fixed field set, `camera_id` only).
- Report complete: on-call questions answered first (4 questions → fields), ownership map table, RED→GREEN evidence (incl. honest admission the GREEN fix was a test-side `None`-in-parametrize bug), command log, zero-sleep proof, assumptions, limitations, files changed. All numeric claims re-verified above.
- Scope respected: allowed-list files only (2 new + report); `camera.py`/`capture.py`/`queue.py`/`health.py`/`reconnect.py`/`common/*` untouched; no commit made (correct — coordinator owns commits); P1-007 not started.

## Findings

### Minor-1: Out-of-order notes bypass window pruning (left-prefix `popleft` loop assumes chronological order); docstring overstates pruning
- Where: `src/eldercare/vision/stream/telemetry.py:252-260` (loop at line 256) vs docstring lines 43-44 ("entries at or below `timestamp - window` are then pruned").
- What: the prune loop only evicts from the head (`while self._frame_times[0] <= cutoff`). Because out-of-order timestamps are *accepted and appended at the tail* (brief-mandated, `test_4b`), a stale out-of-order note lands behind newer head entries, the `while` exits immediately, and the stale entry is retained indefinitely — it drains only once the head advances past it, and meanwhile occupies cap slots. Trace: deque `[8.0, 9.0]` (window 5), `note_frame(1.0)` → cutoff `-4.0`, appends → `[8, 9, 1]`, head `8 > -4`, loop exits, stale `1.0` retained; `frame_window_size` reports 3 while only 2 are in-window. Consequences are bounded: **fps is unaffected** (`snapshot()` full-scans with strict `>`, line 279), memory is still capped at 16384, and the real capture path uses a monotonic clock (non-decreasing notes → deque sorted → pruning exact), so production behavior is correct. The sharp edge is only under explicit-timestamp floods of stale notes: cap eviction is positional (leftmost), so a stale-tail flood could evict good in-window head data and drive fps to `None` despite a live camera.
- Why Minor, non-blocking: externally visible metric (fps) always correct; memory bounded regardless; production path exact; brief's prune test (`test_4`) uses in-order notes and passes. Fix options (implementer discretion, later touch): (a) narrow the docstring to "head-prefix pruning; out-of-order stale entries drain as the head advances, fps always computed by full scan"; (b) replace the loop with a full-deque filter (O(n) per note — fine at capture rates, keeps `frame_window_size` exact); (c) prune relative to `max(noted)` instead of the just-noted ts. Suggested (a) at minimum, one line.

### FYI-1: Snapshot assembly is non-atomic across components (read skew under concurrent mutation, by design)
- Where: `telemetry.py:282-295` — six independent reads (3 queue properties, 2 reconnect attributes, 2 health properties) with no global lock.
- A concurrent `put`/`attempt`/`notify_frame` between reads can mix pre- and post-mutation values in one snapshot (e.g. `submitted` from before a `put`, `depth` from after). Each field is individually consistent; the combination is best-effort. This is the documented acquire-copy-release design (no telemetry lock may be held across component calls, precisely to avoid deadlock), and any global atomicity would require locking component internals telemetry must not touch. No action; noting only so a future task doesn't "fix" it with a cross-component lock.

### FYI-2: MAX-cap eviction is positional (oldest-appended), not oldest-timestamped
- Where: `telemetry.py:258-259`.
- In-order these coincide and the cap keeps the freshest data; under out-of-order floods (see Minor-1) positional eviction can drop in-window entries while retaining stale tail entries. Brief-mandated cap, conservative (under-report) direction, pathological-only trigger. No action beyond the Minor-1 doc consideration.

### FYI-3: `__repr__` intentionally does not validate the clock (never-raises diagnostic)
- Where: `telemetry.py:322-324` — `self._clock()` used raw; a NaN clock yields `fps=None`, a negative clock could inflate repr fps; no `ValueError`, unlike `snapshot()`.
- Correct as-is: `__repr__` must never raise, and repr fps (live clock) may legitimately differ from `snapshot(now=...)` fps. Noting only so a future consistency pass doesn't "fix" it into raising.

### FYI-4: `camera_id` is mirrored blindly (trust boundary sits upstream)
- Where: `telemetry.py:203` (no validation, unlike `health.py:120-121`) → rendered in snapshot + `__repr__`.
- The credential-free tests pass because `CameraConfig` pattern-validates ids upstream (noted in the class docstring, lines 180-181) and telemetry holds no URLs/config of its own. A pathological `camera_id` containing `@`/URL text would be mirrored verbatim — but that is upstream's contract to enforce and the logger's layer to sanitize, not telemetry's. No action.

## Counts

- Critical: 0 — Important: 0 — Minor: 1 — FYI: 4
