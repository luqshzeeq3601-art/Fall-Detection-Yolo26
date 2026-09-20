# P1-003 Fresh Review — Bounded latest-frame queue + P1-002 minor closure (read-only)

- Target: `eldercare-vision/src/eldercare/vision/stream/queue.py` (new, 142 lines),
  `eldercare-vision/src/eldercare/vision/stream/capture.py` (minor diff),
  `eldercare-vision/tests/unit/test_frame_queue.py` (new, 315 lines),
  `eldercare-vision/tests/unit/test_capture.py` (append-only +47 lines)
- Base: git HEAD `b9431db`; working tree reviewed read-only (no repo files modified by reviewer except this review).
- Brief: `eldercare-vision/docs/task-briefs/P1-003.md` (criteria a–g, forbidden scope, minor-resolution spec)
- Spec: pack `AGENTS.md` §§9/12, `ARCHITECTURE.md` §4, `CONSTRAINTS.md` §7
- Evidence: `eldercare-vision/docs/task-reports/P1-003.md` + independent tester verdict
  PASS (189 tests) — taken on authority, not re-run (read-only mandate; avoids cache writes).
- Reviewer re-verification: full static read of all four target files + `P1-002-review.md`
  + report; `git status` / `git diff HEAD --stat` / `git diff HEAD` (capture + tests);
  `rg` probes for except/print/logging/blocking-primitives; `ruff check` + `ruff format --check`
  on the four touched files (both PASS, no writes). No pytest execution.

## Verdict: APPROVE

No Critical or Important findings. Two Minor findings (one docs-precision residual,
one test gap on a newly documented branch — both non-blocking, safe as follow-ups).
Correctness, concurrency, API design, minor resolutions, scope, and hygiene all verified.
AC-P1-003a–g judged met on evidence + static re-verification.

## Findings

### [Minor] Residual unscoped "never raises" bullet in `capture.py` module docstring

- Path: `src/eldercare/vision/stream/capture.py:12-13`
  ("Factory exceptions and `isOpened() == False` yield `False` … — never raises for open-failure").
- Minor #1's fix correctly scoped the Failure-semantics section (`:26-32`) and the
  `open`/`read` method docstrings (`:106-112`, `:157-163`) to "`Exception` failures,
  `BaseException` propagates" — but this lifecycle bullet still says "Factory
  exceptions … never raises for open-failure" unqualified, readable literally as the
  original overclaim the P1-002 reviewer flagged (`P1-002-review.md:26-47`).
- Impact: docs precision only; the normative section below it is exact, and the code
  (all guards `except Exception`) is correct. One-word fix ("Factory `Exception`s").
- No behavior change involved; follow-up docs touch.

### [Minor] Newly documented explicit-`release()` arming branch has no direct test

- Paths: `src/eldercare/vision/stream/capture.py:188-203` (docstring + arming code);
  `tests/unit/test_capture.py:391-440` (appended).
- Minor #4 chose document-why-silent (zero behavior change — confirmed via
  `git diff HEAD`: only docstrings/comments/annotation/import in `capture.py`).
  The two appended tests pin the silent side (cleanup error never overwrites the
  open-failure `last_error`, nothing raises, both failed-open shapes). But the other
  half of the aligned contract — "explicit `release()` backend `Exception` arms
  `last_error`" (`:199-202`) — is covered only by code read; no pre-existing test
  exercises a raising backend `release()` (existing `:218-249` cover idempotent/no-throw
  paths only). The appended `_FailingReleaseCapture` fake already supports it, so one
  ~5-line test (`release()` on an opened failing-release fake arms `last_error`) would
  pin the full alignment the brief asked for ("align to ONE documented behavior with a test").
- Impact: test gap only; the branch is 2 lines and obviously correct. Follow-up test.

### Correctness — verified, no findings

- Drop-oldest determinism: `queue.py:93-102` — `len >= maxsize → popleft, dropped += 1,
  append, submitted += 1` under one lock; single code path for all maxsizes.
  FIFO among retained via `deque` + `popleft` on `get` (`:111-114`). Pinned at maxsize 1
  and 2 (`test_frame_queue.py:49-68`), newest-retention after 10 overflows (`:71-81`),
  interleaved FIFO (`:84-95`).
- Put-return semantic (implementer's choice, contract-first): `True` = drop occurred,
  documented in `put` docstring (`:80-90`), pinned (`:98-104`, plus `:51-56`, `:61-68`).
  No doc/code mismatch: class docstring, method docstring, and tests agree.
- Close/clear semantics match docs: `close` idempotent flag (`:121-124`, tested `:156-161`);
  `put`-after-close `RuntimeError("queue is closed")` (tested `:163-168`); `get`-after-close
  drains then `None` (tested `:171-186`); `clear` empties with monotonic counters
  (tested `:127-150`); close preserves counters (tested `:188-197`). Rejected (closed) puts
  are not counted in `submitted` — consistent with "accepted puts" (`:57-60`).
- Counter exactness: `submitted`/`dropped`/`depth` pinned incl. `n=7 → dropped=n-2`
  (`:107-114`) and post-clear monotonicity (`:127-142`). maxsize=1 repeated-overflow
  exactness is not separately pinned (only single overflow at maxsize 1), but the
  overflow path is maxsize-independent — acceptable, see FYI.
- Closed-queue races: confirmed no blocking exists — `queue.py` contains no
  `wait`/`sleep`/`Condition`/`Semaphore`/`Event` (rg-clean); every method is a single
  `with self._lock` section, so there is no close-while-blocked hazard by construction.
- Exception safety inside lock: all critical sections use `with self._lock` (releases on
  any unwind, incl. the documented closed-`put` raise at `:94-95`). Nothing inside the
  lock invokes user code: `deque.popleft/append/clear`, `len`, int/bool stores only —
  `append(frame)` stores the opaque reference without touching the payload, so no payload
  `__eq__`/hook can raise mid-section. `__str__` delegates to `__repr__` without nesting
  the non-reentrant lock (`:138-139` vs `:129`) — no self-deadlock.

### Concurrency — verified, no findings

- Lock coverage complete: every mutable-state access (`_buffer`, `_submitted`, `_dropped`,
  `_closed`) is under `self._lock` in `put`/`get`/`clear`/`close`/properties/`__repr__`
  (`queue.py:59-78, 93-135`). `maxsize`/`_maxsize` read lock-free (`:51-54`, `:96`) is safe
  (immutable after construction). `__init__` needs no lock (pre-share).
- No I/O in critical sections: rg-clean for print/logging/socket/file ops; invariant stated
  in comments at both lock sites (`:91-92`, `:109-110`); `clear`/`close`/`__repr__` bodies
  likewise pure. No GIL hand-waving: explicit `threading.Lock`, no GIL-dependent reasoning
  in code or report.
- Stress test adequate: 2 producers × 2000 puts + 2 consumers on `maxsize=2`,
  `join(timeout=30)` with deadlock asserts (`test_frame_queue.py:292-300`), `depth <= maxsize`
  sampled under load (`:279-281`), post-drain invariant
  `submitted == received + dropped + depth` and `dropped == total - received` (`:308-314`).
  Threads are non-daemon with timeouts — correct shape for a deadlock detector.

### API design — verified, no findings

- Payload-agnosticism holds: `Generic[_T]` (`queue.py:17-20`), zero attribute access on
  `frame`, no length/equality assumptions; tests use ints/strings/bytes/`object()`
  with identity check (`test_frame_queue.py:226-234`). No `Frame` contract invented —
  per forbidden scope. `Generic` over `Any` is sound: preserves type info for the future
  `Frame` task; call sites parametrize `LatestFrameQueue[Any]` without friction.
- Counter names (`submitted`/`dropped`/`depth`) match `CONSTRAINTS.md` §11 observability
  vocabulary (queue depth, dropped frames) — stable seam for P1-006, no telemetry code
  present. `__repr__` payload-free by construction (`:126-136`), pinned incl. the
  `object()`-address probe (`test_frame_queue.py:203-220`).

### Minor resolutions (vs `P1-002-review.md`) — verified, no scope creep

1. BaseException overclaim → fixed in module Failure section + `open`/`read` docstrings
   (+ raw-message non-logging note), docs-only. Residual: one unscoped bullet at
   `capture.py:13` (Minor above).
2. Thread-safety undocumented → single-owner contract note on `RtspCapture`
   (`capture.py:79-82`, queue named as the handoff), docs-only, no locks added. Exact.
3. `__exit__` signature → conventional
   `(type[BaseException] | None, BaseException | None, TracebackType | None) -> None`
   with `types.TracebackType` import (`:48`, `:209-215`). No behavior change. Exact.
4. Cleanup-swallow vs arming → document-why-silent with comments at both cleanup sites
   (`:133-138`, `:146-151`) + `release()` docstring note (`:188-194`), two appended tests
   (`test_capture.py:418-440`), zero behavior change. Test gap on the arming half
   (Minor above). `test_capture.py` append-only; `capture.py` diff otherwise doc/comment/
   annotation-only — no sneaky behavior change.
- Scope: `git status`/`git diff HEAD --stat` show only `M capture.py`, `M test_capture.py`
  plus allowed untracked new files (`queue.py`, `test_frame_queue.py`, brief, report).
  No forbidden paths (compose/frontend/CI/config/README/pyproject/common/camera.py)
  touched; stdlib-only (`threading`, `collections.deque`); `stream/__init__.py` still
  docstring-only (no eager re-export — consistent with P1-002 precedent).

### Hygiene — verified, no findings

- Type hints on all public APIs (`queue.py` fully annotated incl. properties/`__str__`);
  `requires-python >= 3.10` so `X | None` + runtime `deque[_T]` are sound.
- No bare `except` anywhere (queue: zero `except`; capture: all `except Exception`,
  the two `except Exception: pass` cleanups now carry the preserving-`last_error`
  comment — deliberate, reviewer-blessed, not silent swallowing).
- No `print` in module or tests (rg-clean). `ruff check` + `ruff format --check` PASS on
  all four touched files (reviewer re-ran, read-only).
- Report completeness: design decisions (put-return + close choices), minor-by-minor log,
  RED→GREEN (`ModuleNotFoundError` → 25/25 → full 189 = 162+25+2, arithmetic consistent),
  concurrency params + wall times, command log with allowed-paths check, assumptions,
  and self-disclosed limitations (non-atomic counter triple, threading-only) all present.

### [FYI] Non-blocking follow-ups (no action required)

- `maxsize` type edge: `maxsize=True` accepted as 1; floats/strs unchecked
  (`queue.py:42-43`). Brief mandates only the `>= 1 → ValueError` rule with the value
  named (done); the `int` hint covers the rest. Fine as-is.
- `clear()`-after-`close()` works (empties buffer, flag retained) but is unspecified in
  the close-semantics docs (`queue.py:116-124`). Behavior is reasonable; one doc line
  could close the gap.
- Counter triple (`submitted`/`dropped`/`depth`) is three separate lock acquisitions —
  self-disclosed in report §7; stress invariant is asserted quiescent (post-join), so
  test-sound. P1-006 should note it only if it ever needs an atomic snapshot.
- Stress-test `errors`/`depth_violations` list-appends are lock-free (GIL-atomic append,
  main-thread read post-join) and consumers busy-spin without sleep — benign for a
  0.03s measurement, no hang risk (no blocking primitives under test).
- N-overflow retention pinned only at maxsize 2 (`:71-81`); maxsize-1 overflow pinned
  once (`:49-56`). Same code path — a parametrized N-overflow test would be belt-and-braces.
- `__exit__` body-propagation test (suggested in P1-002 review) consciously omitted —
  allowed list permits `test_capture.py` appends ONLY for minor #4. Correct call.

## Re-verification note

Reviewer ran no test suite (read-only mandate; avoids `.pytest_cache`/`__pycache__`
writes) and takes the 189-test PASS plus `ruff`/`pytest` green claims on the tester +
implementer-report authority, cross-checked for internal consistency (189 = 162 + 25 + 2;
RED `ModuleNotFoundError` narrative; command log). Every finding above was verified by
static read of the exact cited lines plus `git diff HEAD` and rg/ruff probes recorded
above (all read-only; ruff performs no writes). No repo file was created or modified by
the reviewer except this review itself.

## Counts

- Critical: 0 | Important: 0 | Minor: 2 | FYI: 6
- Verdict: APPROVE (no blocking findings; Minor items safe as follow-ups, none touch
  runtime behavior).

## Re-review (2026-09-20, fresh re-reviewer — fix-loop verification, read-only + this section)

- Scope: ONLY the two Minor findings + `docs/task-reports/P1-003.md` `## Fix loop`.
  Read: `capture.py`, `tests/unit/test_capture.py`, fix log. Ran (read-only):
  `pytest tests/unit/test_capture.py -v` (full + `-k` selection),
  `git diff HEAD --stat` + `git diff HEAD -- capture.py/tests`, `ruff check .`.
  No repo files modified except this section.
- Minor 1 (stale module-docstring bullet, `capture.py:13`) — CLOSED:
  module bullet now reads exact-scoped, matching the normative section + method
  docstrings, no contradiction remaining. Module (`capture.py:10-14`):
  "Factory ``Exception``s and ``isOpened() == False`` yield ``False`` plus a
  sanitized ``last_error`` — never raises for open-failure ``Exception``s
  (``BaseException`` propagates)." Normative Failure section (`:27-33`):
  "open/read return-``False``-never-raise for ``Exception`` failures.
  ``BaseException`` … propagates by design". `open` docstring (`:107-112`):
  "Never raises for open-failure ``Exception`` subclasses … ``BaseException``
  propagates." `read` docstring (`:158-163`): "Never raises for read-failure
  ``Exception`` subclasses … ``BaseException`` propagates." All four agree.
- Minor 2 (untested explicit-release arming branch) — CLOSED: new test exists at
  `tests/unit/test_capture.py:443-452`
  (`test_explicit_release_backend_error_arms_last_error`, reuses
  `_FailingReleaseCapture` opened+raising `release()`): opens `True`, `release()`
  does not raise, drops handle (`is_opened is False`), arms sanitized
  `last_error` containing "cleanup release boom". Proof: `-k` selection
  `1 passed, 23 deselected`; full file `24 passed in 0.22s` (tail verified).
- Zero behavior change — CONFIRMED: `git diff HEAD --stat` shows only
  `capture.py` (docstring/comment/annotation, cumulative P1-003 scope) +
  `test_capture.py` (+59 additions only). `capture.py` diff hunks are
  module/Failure/`open`/`read`/`release` docstrings, two preserving-`last_error`
  comments on pre-existing `except Exception: pass`, `TracebackType` import +
  `__exit__` annotation-only signature; no control-flow/`except`/`return`/
  assignment logic touched. Test diff is append-only (fake + 3 tests, last one
  the fix-loop addition). Fix-log claim matches.
- Gates — CONFIRMED: re-reviewer spot-ran `ruff check .` → `All checks passed!`.
  Fix report cites `ruff check`/`ruff format --check` PASS + `pytest -v`
  190 passed (189+1) — consistent with the 24/24 `test_capture.py` run here.
- New findings: none (no Critical/Important/Minor/FYI beyond the two closed minors).

RE-REVIEW: APPROVE — minors closed
