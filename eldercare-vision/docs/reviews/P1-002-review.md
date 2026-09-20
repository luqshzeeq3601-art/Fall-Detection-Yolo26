# P1-002 Security Review — RTSP capture abstraction (fresh reviewer, read-only)

- Target: `eldercare-vision/src/eldercare/vision/stream/capture.py` (new, 196 lines),
  `eldercare-vision/tests/unit/test_capture.py` (new, 393 lines),
  `eldercare-vision/pyproject.toml` (dependencies only, +2 lines)
- Base: git HEAD `e676ec1`; working tree reviewed read-only (no repo files modified by reviewer).
- Brief: `eldercare-vision/docs/task-briefs/P1-002.md` (criteria a–g, forbidden scope).
- Spec: pack `AGENTS.md` §§9/11/12, `CONSTRAINTS.md` §§7–9, `PRD.md` FR-002.
- Evidence: `eldercare-vision/docs/task-reports/P1-002.md` + independent tester verdict
  PASS (162 tests: 141 pre-existing + 21 new).
- Reviewer re-verification: static read of all three target files + `redaction.py`,
  `logger.py`, `camera.py`, `stream/__init__.py`; `git status` / `git diff HEAD`;
  `rg` probes for cv2-confinement and forbidden scope; live read-only probes with
  `PYTHONDONTWRITEBYTECODE=1` and dummy creds only (no pytest execution, to avoid
  writing `.pytest_cache`/`__pycache__` into the tree).

## Verdict: APPROVE

No Critical or Important findings. Four Minor findings (docs precision / robustness
notes, all non-blocking, safe to defer to P1-003). Security posture is clean:
sanitizer reuse, no credential surface on any path, no exception-chaining leak,
no `__rich_repr__`-style sibling needed, dep delta exact, scope respected.

## Findings

### [Minor] No-throw docstring overclaims: `BaseException` from the factory propagates

- Paths: `src/eldercare/vision/stream/capture.py:97-141` (`open`), `:143-171` (`read`),
  `:173-183` (`release`); docstring `:26-30` ("open/read return-`False`-never-raise").
- Re-verification (live probe, dummy creds): factory raising
  `KeyboardInterrupt("intr rtsp://dummyuser:dummy-pass-123@…")` propagates out of
  `open()` uncaught; `last_error` stays `None`. Same holds for `read`/`release`
  backends raising `BaseException` subclasses (`SystemExit` probed on the
  never-opened path shape). Factory returning `None` is handled gracefully
  (`AttributeError` → sanitized `last_error`, `False`, probed clean) — only
  `BaseException` escapes, because every guard is `except Exception`.
- Impact: docs precision only. Catching `BaseException` would be *worse*
  (swallowing `KeyboardInterrupt`/`SystemExit` is an anti-pattern), so the code is
  correct and the tests (which use `RuntimeError`, i.e. `Exception`) pin the
  specified behavior. But "never raises for open-failure" read literally is false.
- Fix (1 line, optional): scope the contract to "`Exception`-subclass failures",
  e.g. "Never raises for open/read *`Exception`*-failure; `BaseException`
  (cancellation) propagates by design." Also note the propagating `BaseException`
  object itself still carries the raw factory message (probed: dummy password
  present in `str(exc)`) — unavoidable and out of scope (it is the caller's own
  exception object, never logged/stored by this module), but worth one doc line
  so P1-003 knows not to log a cancelled-open's exception raw.

### [Minor] Thread-safety is neither handled nor documented

- Paths: `capture.py:73-90` (mutable seam state `_handle`/`_last_error`, no lock);
  `open()` `:103-104` (release-then-create is two steps, not atomic).
- Re-verification (static): `read()` snapshots `self._handle` locally (`:149`) so a
  concurrent `release()` cannot crash it (stale-handle use is benign), but two
  concurrent `open()` calls can interleave release/create and leak one backend
  handle, and `last_error` can be clobbered across threads.
- Impact: negligible for the intended single-owner capture-loop use, but the
  single-owner assumption is nowhere stated — the module docstring documents
  lifecycle, failure semantics, and cv2 differences, but not the threading model.
- Fix (1 line, optional): doc note such as "Not thread-safe; a single capture loop
  must own each instance." If P1-003 shares instances across threads, add a lock
  there, not here (keeps this seam minimal per brief).

### [Minor] `__exit__` signature is imprecise (behavior is correct)

- Path: `capture.py:189`
  (`def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None`).
- Re-verification (live probe): body `ValueError` propagates and the backend is
  still released exactly once — falsy `None` return is the correct propagate
  semantic, matching the docstring (`:22-24`). The suite covers happy-path and
  open-failure CM paths; body-propagation is untested but probed clean here.
- Fix (cosmetic, optional): `exc_type: type[BaseException] | None` etc. No
  behavior change. Also consider one test asserting body-exception propagation +
  release (mirrors the probe above).

### [Minor] Cleanup `except Exception: pass` on failed-open release swallows silently

- Paths: `capture.py:123-126`, `:134-137` (failed-open backend `release()` errors
  discarded) vs `:179-182` (`release()` arms `last_error` on backend errors).
- Impact: negligible — the open is already returning `False` with `last_error`
  set, the seam handle is dropped either way, and no-throw holds. The
  inconsistency (two release paths, two policies) is a readability nit.
- Fix (optional): one comment ("cleanup release must not overwrite the
  open-failure `last_error`") or arm a suppressed-note. Either way, no test gap:
  `test_release_after_failed_open_no_throw` (`test_capture.py:236-245`) pins the
  no-double-release behavior.

### [FYI] `__rich_repr__`-style siblings — confirmed not needed, no leak

- Paths: `capture.py:192-196` (`__repr__`/`__str__` only).
- Re-verification (live probe): `hasattr(RtspCapture, "__rich_repr__")` is
  `False`; plain objects fall back to `__repr__` under rich/pretty printers, and
  `repr(cap)` on a credentialed config shows only
  `RtspCapture(camera_id='cam-01', opened=False)` (probed). Unlike P1-001's
  pydantic model (which needed the `__rich_repr__` fix), there is no framework
  dunder bypass here. `vars(cap)` exposes `_config` with the raw URL — by design
  (the capture layer must dial it), not a leak surface; note `repr` reads only
  `config.camera_id` and never `str(config)`.

### [FYI] Exception chaining — no surface in this module

- `rg "raise" capture.py` matches docstring text only; the module contains zero
  `raise` statements, so there is no `raise … from` carrying raw values (the
  P1-001 residual does not recur). All failure paths store
  `sanitize_exception_message(str(exc))` and log the already-sanitized
  `last_error` (double-sanitized at format time by the P0-006 logger — defense
  in depth, verified by reading `logger.py:121-134,171-191`).

### [FYI] API design — sound; two brief-directed tradeoffs recorded

- Protocol minimality (`capture.py:56-70`): exactly the three installed-build
  members (`isOpened`/`read`/`release`), names verified against the report's
  live OpenCV probe. DI seam soundness: factory resolved via module-attribute
  lookup at each `open()` (`:105`), so `monkeypatch.setattr(cv2, …)` intercepts
  (area-9 tests pin this, `test_capture.py:337-366`).
- `cv2` imported at module top (`:48`): consequence is that even cv2-free
  consumers (DI fakes) pay the import — but this is brief-mandated
  ("declare EXACTLY what the new module top-level-imports") and the dep is
  declared; blast radius is limited because `stream/__init__.py` is
  docstring-only (no eager re-export), so only direct importers require cv2.
  A `TYPE_CHECKING`-style lazy import would be purer library design but would
  contradict the brief's explicit accounting rule. Accept as-is.
- `numpy` runtime-imported for an annotation only (`:49`, used at `:143`);
  with `from __future__ import annotations` (`:43`) it could be
  `TYPE_CHECKING`-only — but the brief explicitly anticipates
  ("If `numpy` is imported for annotations at runtime, declare `numpy>=1` too")
  and the report declares it with installed-version proof (2.2.6). Compliant;
  the hard runtime edge is harmless.
- N802 `noqa` (`:60`, mirrored in test fake at `test_capture.py:51`): justified —
  the name is dictated by the installed OpenCV API and ruff selects `N`
  (`pyproject.toml:26`). No bare `except` anywhere in the module (all guards
  are `except Exception`), satisfying AGENTS.md §9.

### [FYI] `last_error` discipline — matches the brief; two P1-003 notes

- Cleared on successful open (`:139`) and successful read (`:170`); armed
  (sanitized) on every failure path; preserved across `release()` — exactly the
  brief's "cleared on successful open/read" rule (clearing test at
  `test_capture.py:372-393`). Read-when-closed arms `last_error` with a routine
  "not open" message and logs WARNING (`:150-155`): reasonable, but if P1-003
  polls `read()` on a closed capture this becomes log noise — consider DEBUG
  for that single path later. No change required here.

### [FYI] Scope, confinement, and report completeness — confirmed clean

- `git status --short`: only `M pyproject.toml` plus four allowed untracked
  files (`docs/task-briefs/P1-002.md`, `docs/task-reports/P1-002.md`,
  `src/eldercare/vision/stream/capture.py`, `tests/unit/test_capture.py`).
  `git diff HEAD --stat`: `pyproject.toml | 2 ++` only — no forbidden-file
  changes (`common/*`, `camera.py`, compose/frontend/CI/config/README/
  `.env.example` untouched).
- Dep delta exact: `+opencv-python-headless>=4`, `+numpy>=1` — precisely the two
  third-party top-level imports (`cv2`, `numpy`); stdlib + first-party need no
  declaration. Headless choice matches the brief's deployment guidance.
- cv2 confined: `rg "cv2|opencv" src` hits only `capture.py` (real import at
  `:48`, attribute lookup at `:105`, docstring/API-mirror mentions). Test-file
  `cv2` imports are function-local (`test_capture.py:343,361`, monkeypatch
  only) and open no streams — outside `src/` scope per AC-P1-002g.
- No reconnect/queue/health/telemetry code: `rg -i
  "reconnect|backoff|health|telemetry|metric|prometheus|queue"` on `capture.py`
  matches only the docstring's "no reconnect, no queues" scope line. Logging is
  P0-006 reuse (`get_logger("vision", component="stream.capture", …)` at `:85`;
  events `capture.opened/open_failed/read_failed/released`), no URL passed to
  any log call. FR-002 (decode frames when online) is served at the seam level
  without Phase-2 overreach.
- Report completeness: OpenCV version/distribution/API-shape citations (§1),
  RED→GREEN narrative with the corrected test expectation (§3 — code was right,
  test was wrong; the fix direction is sound), full command log (§4), dependency
  justification (§6), cv2-confinement with line ref (§7), and assumptions/
  limitations (§§8–9) all present. The `is_opened`-as-seam-state (not live
  poll) and `(True, None)`-passthrough choices are documented in both report
  and module docstring.

## Re-verification note

Reviewer ran no test suite (read-only mandate; avoids cache writes into the
tree) and takes the 162-test PASS on the tester's authority. Every behavioral
claim in this review was verified by static read plus targeted live probes
(`PYTHONDONTWRITEBYTECODE=1`, dummy `dummyuser`/`dummy-pass-123` in-process
only): factory-returns-`None`, `KeyboardInterrupt`/`SystemExit` propagation,
non-tuple `read()`, degenerate `(True, None)`, body-exception propagation with
release, `BaseException`-on-release handle-drop, double-open handle hygiene,
`None`-config constructor error, `__rich_repr__` absence, and `repr` output —
plus `git status`/`git diff` and `rg` confinement/scope re-runs recorded above.
Probe script lives outside the repo (`Temp/opencode/p1-002-probe.py`); no repo
file was created or modified by the reviewer except this review itself.

## Counts

- Critical: 0 | Important: 0 | Minor: 4 | FYI: 5
- Verdict: APPROVE (no blocking findings; Minor items safe to defer to P1-003).
