# P1-005 Review — Reconnect/backoff (fresh, read-only)

- Target: `src/eldercare/vision/stream/reconnect.py` (328 lines, new) + `tests/unit/test_reconnect.py` (443 lines, new)
- Brief: `docs/task-briefs/P1-005.md` (criteria a–h); Spec: pack `AGENTS.md` §§9,12 + `PRD.md` FR-004 + `CONSTRAINTS.md` §§7–9
- Base: git HEAD `5c3d18f`; working tree adds only the 2 target files + report (+ pre-existing untracked brief input). No tracked file modified.
- Implementer report: `docs/task-reports/P1-005.md`; tester verdict: PASS (264 tests).

## Verdict: APPROVE

No Critical or Important findings. The highest-risk item (lock-vs-sleep) is clean on inspection.

## Re-verification (independent, not trusted from report)

| Check | Result |
|---|---|
| `python -m pytest tests/unit/test_reconnect.py -q` | 31 passed (0.23s) — matches report |
| `python -m pytest -q` (full suite) | 264 passed (0.60s) — matches report's 264 (233 prior + 31 new) |
| `ruff check` on both new files | All checks passed |
| `ruff format --check` on both new files | Already formatted |
| `git status --short` | Only 4 untracked paths (brief input, report, `reconnect.py`, `test_reconnect.py`); zero modifications to tracked files — no forbidden-file changes, no `pyproject.toml`/dep change |
| `time.sleep` in test file / real sleeps | None; full suite 0.60s is itself the zero-sleep proof (a single 3-failure loop would cost 7s real) |
| Bare `except` / `print(` / threads / timers / non-stdlib imports | None found (only `except OverflowError`, line 135; imports are `math`, `threading`, `time`, `collections.abc`, `dataclasses` + allowed repo modules) |

## 1. Concurrency — highest-risk item, investigated first: CLEAN (no finding)

- `src/eldercare/vision/stream/reconnect.py:229-247` — failure path: counters + `delay_for` computed under the lock (lines 229–234), lock released, then logging (235–245) and `self._sleep(delay)` (246) happen **outside** the lock. Sleep does NOT hold the lock.
- `attempt()` pre-check (219–221): stopped flag read under a short lock, then `capture.open()` (222) outside it. Success-path reset (223–226) under a short lock, logging outside.
- `stop()` (196–206): flag flip under lock, early-return if already stopped (idempotent), logging after lock release — exactly one `stopped` line; pinned by `test_7c`.
- `stopped` property (190–194) and `__repr__` (303–315) take the lock only for scalar reads (`sanitize_exception_message` on `camera_id` inside `__repr__` is pure string processing, not I/O).
- `connect_with_retry()` (271–284) never holds the lock across calls — it uses the `stopped` property and `attempt()`, each locking briefly. Single lock, no nesting → no deadlock. `stop()` from another thread (or from inside the injected sleep, cf. `test_7b`) is visible at the next loop-top check (272) without waiting out anything except the one in-flight injected sleep, which is fake in tests and bounded by `max_delay` in production.
- Assumption "one loop thread drives, lock protects flag/counter races" is stated in report §8 and matches `RtspCapture`'s model. Acceptable for this POC core.

## 2. Correctness

- **Delay formula** (`reconnect.py:122-139`): `min(base * mult**(n-1), max)` with `attempt<1`/bool/non-int → `ValueError` (131–132). `attempt=0`/negative correctly rejected (pinned by `test_2c`). `delay_for(10**9)` returns `max_delay` via the `except OverflowError` path (133–138, pinned by `test_2e`) — verified: `**` on huge exponents raises `OverflowError`, caught; residual float-mult overflow would yield `inf`, which `min()` still caps correctly. Edge cases covered.
- **`max_attempts=None` infinite loop**: `connect_with_retry` with cap `None` retries until success or `stop()` — the ONLY exit besides success is `stop()`. This is brief-mandated (`None` = retry until stopped) and disclosed in report §8 ("callers must guarantee a stop path") plus docstring line 258. Confirmed acceptable; no code change needed.
- **Counter reset completeness** (`reconnect.py:222-226`): success resets `attempts`, `consecutive_failures`, AND `last_delay=None`. Restart-at-base proven by `test_5`. Complete.
- **Stop-flag placement**: checked before capture call in `attempt()` (219–221) and at every `connect_with_retry` loop-top (272), but NOT after sleep inside a single `attempt()`. A stop landing mid-sleep takes effect when the sleep returns (next loop-top, no extra capture call — proven by `test_7b`: 1 open, 1 sleep). This is inherent to the injected-sleep design (no interruptible sleep primitive required by the brief) and prompt enough. See FYI-1.
- **Mid-sequence cap override semantics**: `_resolve_cap()` (286–301) precedence override → alias → policy; disagreement → `ValueError`; each override validated `int>=1`, bools rejected. Note the cap counts **per-call loop iterations** (`made`, line 270/274), not lifetime `controller.attempts` — a reused controller with prior standalone `attempt()` history gets a fresh allowance each `connect_with_retry` call, and the `gave_up` log reports per-call `made`. Tests only pin fresh-controller behavior. Harmless here (manager wiring is later), but worth one docstring line. See Minor-2.

## 3. API design

- **Dual-keyword `max_attempts_override` + `max_attempts`: judged Minor (documented-and-pinned acceptable), NOT Important.** Reasoning: the inconsistency originates in the brief itself (body specifies `max_attempts_override`, test area 4 calls `connect_with_retry(max_attempts=3)`), so accepting both is the pragmatic correct resolution — standardizing on one spelling would break one of the brief's own call sites. The implementation documents precedence in the docstring (257–258), rejects disagreement loudly (`test_conflicting_overrides_rejected`), accepts agreement (`test_matching_overrides_agree`), and both spellings are exercised (`test_4` vs `test_5b`). Residual wart is only surface size. Recommendation (non-blocking): pick one canonical spelling when the Stream Manager wires this core (later task) and keep the other as a deprecated alias — no action in P1-005. See Minor-1.
- **`attempt()` public surface**: correct — the brief names it "the unit under test". Public is intended.
- **`stopped` property vs method**: matches brief (`stopped: bool` property, §Requirements) and is used consistently (`test_7a/7c`, loop-top check). Correct.
- **`__repr__` completeness** (`reconnect.py:303-315`): carries `camera_id/attempts/consecutive_failures/stopped`, URL-free by construction (never formats the held `CameraConfig` URL) plus sanitizer defense-in-depth. Omits `last_delay`/policy — acceptable; brief only requires the four fields. See FYI-3 for an optional addition.

## 4. Security

- No URL formatting in the controller: logs carry only `attempt`/`max_attempts`/`delay` numerics + bound `camera_id` (235–245, 275–280); `__repr__` asserts `"rtsp://" not in` text (`test_9`, `test_repr_carries_ids_and_counts_without_url`). Controller adds no `try/except` around `capture.open()` — relies on `RtspCapture`'s documented containment (returns `False` + sanitized `last_error`), with `BaseException` propagating by design, matching `capture.py`'s cancellation philosophy. Adversarial credential tests (`test_6` raising factory embedding password, `test_9` credentialed URL + leaky factory) assert `last_error`/log JSON/`repr` are password-free. Only dummy credentials in-process in tests; no `.env`/real secrets. Clean.

## 5. Hygiene / scope

- Type hints on all public APIs; frozen dataclass policy; no bare `except`; no `print`; no threads/timers spawned (caller drives; `sleep` injected); stdlib-only imports; `ruff check` + `format --check` clean (re-verified). Contract-first docstring covers formula + worked example, honesty rule, stop semantics, and NOT-here list per brief §Contract-first. Report covers formula/example, honesty rule, RED→GREEN, command log, timing proof, assumptions, per-criterion mapping — complete; all numeric claims re-verified above. Scope respected: no MQTT/persistence/telemetry/Phase-2 code; allowed-list files only.

## Findings

### Minor-1: Dual-keyword `max_attempts_override` / `max_attempts` surface wart (accepted, standardize later)
- Where: `src/eldercare/vision/stream/reconnect.py:249-254, 286-301`; tests `tests/unit/test_reconnect.py:232, 267, 433-443`.
- What: two spellings for one cap. Justified by the brief's internal inconsistency; documented, disagreement-rejected, both pinned. No P1-005 change required. Recommend the future manager task nominate one canonical keyword and keep the other as alias.

### Minor-2: `connect_with_retry` cap counts per-call iterations, not lifetime attempts (undocumented)
- Where: `src/eldercare/vision/stream/reconnect.py:269-284` (`made` local vs `self.attempts`).
- What: on a reused controller (prior standalone `attempt()` failures), a new `connect_with_retry(cap)` performs up to `cap` *additional* opens, and `gave_up` logs per-call `made`, not cumulative `attempts`. Behavior is sane; only the docstring should say so in one line (e.g. "cap bounds iterations of this call"). Tests use fresh controllers so both readings coincide. Non-blocking.

### Minor-3: `delay_for` return type is `int` when policy built with ints (frozen dataclass doesn't coerce)
- Where: `src/eldercare/vision/stream/reconnect.py:103-120` (`__post_init__` validates via `_check_delay` but never assigns the coerced `float` back) vs annotation `-> float` (line 122).
- What: `ReconnectPolicy(base_delay=1, multiplier=2, max_delay=30).delay_for(1)` returns `int 1`, not `float 1.0`, contradicting the `-> float` hint. Trivial in practice (defaults are floats; `sleep(int)` works; no test builds int policies except via parametrized invalid cases). Non-blocking; fix is one `object.__setattr__` trio or a documented "floats recommended" note. Left to implementer discretion in a later touch.

### FYI-1: Stop during `attempt()`'s sleep takes effect after the sleep returns
- Where: `src/eldercare/vision/stream/reconnect.py:246` + loop-top re-check line 272.
- No interruptible-sleep primitive exists (or is required); `test_7b` proves prompt exit with no extra capture call. In production the in-flight delay is bounded by `max_delay` (30s default). Inherent to design, already prompt enough. No action.

### FYI-2: `clock` is stored but never read
- Where: `src/eldercare/vision/stream/reconnect.py:173-180`.
- Already disclosed in report §7 (DI/signature stability, future manager use; delays come from policy). Agreed, no action. Flagging only so a future task doesn't "fix" it by adding gratuitous wall-clock reads.

### FYI-3 (optional): `__repr__` omits `last_delay`
- Where: `src/eldercare/vision/stream/reconnect.py:310-314`.
- Brief requires only the four fields present. Adding `last_delay=` would aid log-grepping of backoff state at zero cost. Purely optional; do not churn if untouched.

## Counts

- Critical: 0 — Important: 0 — Minor: 3 — FYI: 3

## Re-review (2026-09-20, fresh, read-only + live probe)

RE-REVIEW: APPROVE — minors closed.

- Minor-2 (cap-semantics doc): CLOSED. `reconnect.py:261-262` now reads "The cap bounds iterations of this call only; lifetime `attempts` is cumulative and unaffected by the cap." Accurate on inspection: `connect_with_retry` bounds local `made` (271-276) while `attempt()` accumulates `self.attempts` (229-230); `gave_up` logs per-call `made`.
- Minor-3 (int-vs-float return): CLOSED. `reconnect.py:139` is `return float(min(raw, self.max_delay))`; overflow path `:138` already `float(...)`. Live probe: int-built `ReconnectPolicy(1,2,30).delay_for(1)` → `1.0 float True`; `delay_for(6)` → `30.0 float True`; defaults `delay_for(1)` → `1.0 float`. Matches `-> float` hint; sleep/math behavior unchanged (`float(int)==int` numerically).
- Scope / zero behavior change: `git diff HEAD --stat` empty (no tracked-file modification); `git status --short` shows only 5 untracked paths (brief input, report, this review, `reconnect.py`, `test_reconnect.py`). No test changes; no tracked files touched.
- Dual-keyword API untouched (Minor-1 deferral intact): `connect_with_retry(max_attempts_override, *, max_attempts)` signature (249-254) + `_resolve_cap` precedence override → alias → policy with disagreement `ValueError` (288-303) still present.
- Gates (spot-run): `python -m pytest -q` → 264 passed; `ruff check .` → All checks passed; `ruff format --check reconnect.py` → already formatted.
- New findings: none (no Critical/Important/Minor/FYI added).
