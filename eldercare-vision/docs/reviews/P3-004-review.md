# P3-004 Review — Track expiry/cleanup

Verdict: **APPROVE**

## 1. Scope / snapshot

- Brief (binding): `docs/task-briefs/P3-004.md` — additive-only `expire_stale(now, *, max_idle_seconds)` on
  `TrackHistory` in `src/eldercare/vision/tracking/history.py`; exact `>` boundary; AC-P3-004a..g; forbidden scope
  (temporal features, reactivation heuristics, clocks/sleeps/locks/threads, all other `src/` files, existing tests).
- Implementer report (treated as UNVERIFIED claim): `docs/task-reports/P3-004.md`.
- Reviewed diff (worktree, uncommitted): `history.py` +67/−4; new `tests/unit/test_track_expiry.py` (25 tests);
  untracked `docs/task-briefs/P3-004.md`, `docs/task-reports/P3-004.md`. `__init__.py`, `pyproject.toml`,
  all other tracked files untouched.
- Pack references: AI_SPEC §5 (history keyed by `(camera_id, track_id)` — reused as-is, no tracking change),
  CONSTRAINTS §§7–8 (no unbounded buffers — expiry *reduces* key growth; type hints + Ruff + pytest, no bare
  `except`/hidden globals — clean), TASK_SKILL_MATRIX P3-004 row (TDD, IMPL+TEST, "stale tracks removed" — met).

## 2. Verification — fresh execution (exact outputs)

Env: `eldercare-vision/.venv\Scripts\python.exe` (venv packages untouched). Ruff 0.16.8 via isolated
`--target $env:TEMP\ruff-review-p3004` on system Python 3.14.2 / pip 25.3 (same version the report used).

| Gate | Fresh result |
|---|---|
| Focused `pytest tests/unit/test_track_expiry.py -q` | `25 passed in 0.31s` |
| Full `pytest -q` | `602 passed in 2.85s` |
| Prior-only `pytest -q --ignore=tests/unit/test_track_expiry.py` | `577 passed in 3.14s` (577 prior green, unmodified; 602 = 577 + 25) |
| Relevant P3/P2 suites (history, observation, pose tracker, pipeline, adapter) | `165 passed in 1.41s` (matches report) |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `137 files already formatted` (report said 136; both pass — FYI-1) |
| `git diff --name-only` (tracked) | only `eldercare-vision/src/eldercare/vision/tracking/history.py` |
| `git diff --stat` | `1 file changed, 67 insertions(+), 4 deletions(-)` |
| New-test collection | 25 tests, ≤ 30 cap met |

Historical (report) claims spot-checked, not trusted: RED 23-fail pre-state not re-runnable post-implementation
(code already GREEN); all GREEN numbers above re-measured fresh and match.

## 3. AC-by-AC verdicts

- AC-P3-004a (latest-timestamp basis, strict `>` boundary, multi-key independence): **PASS** — §4b probes + tests
  `test_boundary_*`, `test_expiry_uses_latest_timestamp_not_earliest`, `test_mixed_freshness_*`, `test_multi_camera_*`.
- AC-P3-004b (survivors bit-exact, ordering intact): **PASS** — §4c probe (`bit-exact: True`, order `[18.0, 19.0, 20.0]`).
- AC-P3-004c (idempotency, reuse-fresh, bulk): **PASS** — §4d/§4e probes (second call `()`; reuse snapshot `== (fresh,)`,
  no ghosts; remove→recreate ages from new append; bulk 1000 keys, all returned, store `len 1`, 0.0024 s).
- AC-P3-004d (fresh tuple, documented insertion order, no mutable internals): **PASS** — §4f probes
  (`type is tuple`, element tuples, mutation-isolated, insertion order `(5,3,9,1)`, distinct objects per call).
- AC-P3-004e (fail-closed + no clocks/sleeps/threads): **PASS** — §4g/§4i (bool/non-numeric→`TypeError`,
  NaN/±Inf/negative→`ValueError`, messages name the offender, store unchanged per value, positional rejected;
  AST + `sys.modules` proofs, imports stdlib-only + `math`).
- AC-P3-004f (compactness ≤ 30, no duplicated coverage, CPU-only): **PASS** — 25 tests; new file asserts no
  append/ordering/eviction/snapshot/converter internals (grep §4i finds only a docstring mention + the `_history`
  builder default); zero sleeps; no framework imports in `src` or tests.
- AC-P3-004g (gates + additive diff + no dep changes): **PASS** — §2 gates green; −4 deletions are
  module-docstring rewording only (two hunks: eviction paragraph, What-is-NOT paragraph); `pyproject.toml` untouched.

## 4. REVIEWER-CRITICAL checks a–i (live probes, TEMP-only scripts)

a. **Additivity — PASS.** `git diff` hunks: 2 docstring-only deletions + `import math` + `_check_idle_time` +
   `expire_stale` + method docstring. AST comparison HEAD-vs-worktree (utf-8 decoded): all 9 pre-existing
   `TrackHistory` methods identical; only addition is `expire_stale`; all 3 pre-existing module functions identical;
   only addition is `_check_idle_time`. (One transient `snapshot: False` under a cp1252-decoded `git show`
   was a reviewer-side mojibake artifact — FYI-2; re-run with utf-8 gives identical dumps, 1342 == 1342.)
   Plus 577 prior tests green unmodified.
b. **Exact boundary — PASS.** Fresh probes: idle 4.999→`()` survive; idle 5.0→`()` survive; idle 5.001→expired;
   non-round (`ts=3.14159`, `max_idle=2.71828`): `==` survives, `+1e-9` expires.
c. **Survivor integrity — PASS.** Post-expiry `snapshot(cam-a,2)` bit-exact vs pre-expiry (`== tuple(survivor_obs)`),
   order preserved; other keys untouched; stale key `snapshot == ()`.
d. **Idempotency + reuse + remove→recreate — PASS.** Repeat equal-args call returns `()`; post-expiry `append`
   yields snapshot `(fresh,)` with `old not in` it and re-expiry `()`; `remove`→`append(ts=18.0)`→expiry `()`, len 1.
e. **Bulk reclamation — PASS.** 1000 stale + 1 fresh: all 1000 returned in insertion order, `keys == ((cam-a,1000),)`,
   `len == 1`, 0.0024 s. Collect-then-delete path (tuple built before any `del`) — no mutate-during-iteration.
f. **Fresh-tuple return — PASS.** `type(expired) is tuple`, elements are tuples, exact value; clearing a `list()`
   copy leaves the store intact and the next call still `()`; insertion order `(5,3,9,1)` preserved and documented
   in the method docstring ("key-insertion (dict) order"); two empty calls return equal-but-distinct objects.
g. **Fail-closed matrix — PASS.** All of `None/True/False/"20.0"/(20.0,)/NaN/±Inf/-1.0/-0.5` for each of `now` and
   `max_idle_seconds` raise (`bool`/non-numeric→`TypeError`, NaN/Inf/negative→`ValueError`), messages name
   `now`/`max_idle_seconds`, store (snapshot + keys) unchanged per value; positional `max_idle_seconds` raises
   `TypeError` with store intact (keyword-only signature confirmed).
h. **now<last + max_idle=0.0 — ACCEPT as sound.** `now < last` (idle negative) survives: correct under the brief's
   exhaustive rule (expires iff `now − last > max`, and negative idle never exceeds a non-negative limit); the brief
   defines no such error and P3-003 append monotonicity is the stated guard. `max_idle_seconds=0.0` valid with
   only-positive-idle expiring (`(cam-a,2)` expired, `(cam-a,1)` at `now` survives): correct — the brief rejects only
   negatives, and 0.0 is the coherent degenerate "reclaim anything idle at all" policy. Both documented + tested
   (`test_zero_max_idle_expires_only_positive_idle`).
i. **No forbidden code / no duplication — PASS.** `history.py` imports: `math, collections, dataclasses, typing`
   (+ intra-package `observation`) — stdlib-only addition; AST: no clock/sleep/lock/thread calls or attributes;
   `sys.modules` probe: no `torch`/`ultralytics`/`cv2`, no `time`/`threading`/`asyncio`/`concurrent` introduced.
   Test-file grep hits are the framework-freedom proof itself. No temporal/expiry-heuristic/sampling/background code;
   no duplication of history/observation/converter coverage (§2 table). `__init__.py` byte-identical (empty diff).

## 5. Counts

- Tests: 25 new (cap 30), 577 prior, 602 full, 165 relevant P3/P2 — all green, fresh.
- Ruff: `check` pass, `format --check` pass (137 files), version 0.16.8 isolated.
- Diff: +67/−4, deletions docstring-only.

## 6. Findings

No Critical, no Important.

- Minor-1 — none. (No code, test, or doc defect found; nothing blocks approval.)
- FYI-1 — `ruff format --check` reports `137 files already formatted` vs the report's `136 files already formatted`
  (`history.py:punct` unchanged, both pass, ruff 0.16.8 identical). Likely file-count drift, not a code issue.
  Evidence: §2 table. No action required.
- FYI-2 — Reviewer-side encoding note: comparing `git show` output decoded as cp1252 vs utf-8 once flagged
  `snapshot` AST-unequal (arrow `→` mojibake). Re-run with `encoding="utf-8"` gives identical dumps.
  Evidence: `C:\Users\luqma\AppData\Local\Temp\review-p3004-snap.py` output `wrote 1342 1342`, prefix equal.
  No action required.
- FYI-3 — `if buffer` guard in `expire_stale` (`history.py:235`) conservatively retains hypothetical empty buffers
  instead of dropping them. Unreachable via the public API (buffers are created with their first append and removed
  whole); retaining is the safe direction. Documented in the report's Assumptions. No action required.

## 7. Final verdict

**APPROVE** — all AC-P3-004a..g pass on fresh evidence; checks a–i pass with live probes; additive-only diff
verified hunk-by-hunk; gates green (602 pytest, 577 prior unmodified, ruff check + format). No unresolved
Critical/Important findings, so no scoped fix is prescribed. Do NOT start P3-005 (coordinator owns next dispatch);
no commit made (coordinator owns commits).
