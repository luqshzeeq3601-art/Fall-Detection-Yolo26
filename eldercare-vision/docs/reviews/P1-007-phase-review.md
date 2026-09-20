# P1-007 Phase Review — Phase 1 gate (fresh Phase Reviewer, read-only)

- Base: git HEAD `551728b` (confirmed via `git rev-parse HEAD`; `git log` top entry
  `551728b P1-006: read-only capture telemetry with honest FPS snapshot`).
- Working tree: clean except untracked `docs/task-briefs/P1-007.md` (this gate's brief
  input). No tracked-file modifications. Reviewer modified nothing except this file.
- Method: independent re-run of the FULL validation set at HEAD + static re-read of all
  six `vision/stream/` modules + live read-only probes (dummy values only). Prior
  reports/reviews were cross-checked, never trusted.

## Verdict: APPROVE

No Critical or Important findings. Phase 1 meets every matrix done-state (P1-001…P1-006),
the IMPLEMENTATION_PLAN Phase 1 Build/Test items, the METHODOLOGY §7 gate
("Stable RTSP ingest + reconnect") at the component-complete level the plan specifies,
and AC-P1-007a–g subject to the two rulings below (assembly → Minor + Phase 2
integration point; dual-keyword → explicitly closed). No fix loop required.

## Scope inputs read

- Brief: `eldercare-vision/docs/task-briefs/P1-007.md` (criteria a–d, f, g — reviewer scope).
- Pack: `TASK_SKILL_MATRIX.md` §§4–7, `IMPLEMENTATION_PLAN.md` (Phase 1 section),
  `METHODOLOGY.md` §7, `PROGRESS.md` (§§1–5, 8, 12), `PRD.md` (FR-001–FR-005).
- Repo: full `src/eldercare/vision/stream/` tree (`camera.py`, `capture.py`, `queue.py`,
  `health.py`, `reconnect.py`, `telemetry.py`, `__init__.py`) + `pyproject.toml`,
  `docker-compose.yml`, `.env.example`.
- Prior: `docs/task-briefs/P1-001.md`…`P1-006.md`, `docs/task-reports/P1-001.md`…`P1-006.md`
  (incl. all Fix-loop appendices), `docs/reviews/P1-001-review.md`…`P1-006-review.md`
  (incl. all Re-review appendices).

## Findings (new, this gate)

### [Minor] Assembly gap: six tested components, no wired stream-manager loop (see ruling §1)

- Paths: `src/eldercare/vision/stream/` (six modules present; no `manager.py`, no loop,
  no thread ownership anywhere — verified by tree listing + `manager` grep: only
  docstring mentions at `camera.py:1,24`, `reconnect.py:150,157`).
- The IMPLEMENTATION_PLAN Phase 1 Exit ("Camera stream runs independently of AI") is
  claimable ONLY in its scoped sense: all stream-side machinery exists with zero AI
  dependency (no ultralytics/cv2-inference/tracking code anywhere — leakage grep clean).
  It was never demonstrated as a running loop: nothing pumps
  `capture.read() → queue.put() → health.notify_frame() → telemetry.note_frame()` or
  drives `health.poll() + reconnect.attempt()`, and no such integration test exists
  (closest: P1-005 test_8 health+reconnect honesty; P1-006 test_6 trio aggregation).
- Why Minor, not Important: no matrix row requires assembly (matrix §4 lists only
  P1-001…P1-006 components + this gate); every plan Build/Test item has unit coverage;
  all briefs deliberately forbade network/devices/threads-spawned-in-components, so an
  operational loop was never in scope. Creating it now would expand the frozen plan.
- Recommendation: documented Phase 2 integration point (NOT a new Phase 1 task) — see §1.

### [FYI] `PROGRESS.md` §3 still carries stale Phase-0 template text

- Path: `eldercare_muse_subagent_pack/PROGRESS.md` §"3. Current Task" (describes
  "Initialize repository and quality baseline" while §§1–2/12 correctly track P1-007).
- Pack files are forbidden to this gate, so no fix here; coordinator should correct the
  §3 template when closing P1-007. Content accuracy (§§1–2, 4–5, 8, 12) verified below.

## Ruling §1 — Assembly question (mandatory): Exit claimable with caveat; Minor; Phase 2 integration point

- Judgment: the Phase 1 Exit **can** honestly be claimed **iff** worded as
  **component-complete**: "Camera-stream machinery (config → capture → queue → health →
  reconnect → telemetry) is implemented, unit-tested (228 Phase-1 tests, fakes-only),
  and runs with zero AI dependency." It can **not** be claimed as "a wired ingest loop
  was demonstrated" — no manager class, no driver loop, no end-to-end frame-pump test
  exists, and real-camera ingest remains unproven (by plan design: network/devices were
  forbidden in every Phase 1 brief).
- Severity: **Minor** (non-blocking for Phase 1 COMPLETE — reasoning in Findings above).
- Recommendation: **documented Phase 2 integration point**, not a new task. Concrete
  terms: (a) P2-004 ("Integrate pose into live pipeline") takes the stream-manager
  wiring as an explicit precondition (capture-loop thread owning `RtspCapture`,
  `queue.put` handoff, `health.poll` driver, `reconnect` driver, `telemetry.note_frame`
  fan-in, lock-ordering across the loop); (b) that task owns the first integration test
  pumping a fake capture end-to-end through queue→health→telemetry with exact
  drop/transition/fps assertions; (c) Phase 1 COMPLETE is recorded with this caveat,
  not as "ingest demonstrated live".

## Ruling §2 — Dual-keyword item (mandatory): EXPLICITLY CLOSE (option b). No third option taken.

- Status quo verified live: `connect_with_retry(self, max_attempts_override=None, *, max_attempts=None)`
  (`reconnect.py:249-254`); `_resolve_cap` precedence override → alias → policy with
  disagreement `ValueError` (`reconnect.py:288-303`); both spellings pinned by tests,
  conflict/agreement cases pinned; fix-loop history shows Minor-2/3 closed around it
  without touching it.
- Reasoning for close-over-standardize: (a) the inconsistency originates in the P1-005
  brief itself (body mandates `max_attempts_override`, test area 4 mandates
  `connect_with_retry(max_attempts=3)`) — standardizing now would violate one brief call
  site and force edits to already-passing pinned tests; (b) the dual acceptance is
  documented (docstring precedence rule), disagreement fails loud, behavior is sane;
  (c) there are zero in-tree callers (no manager exists), so no caller confusion is
  possible today; the future manager task nominates one canonical spelling and keeps
  the other as alias. Standardization cost exceeds any benefit; deferral is forbidden
  by this gate, so: **explicitly closed, harmless-by-construction, pinned by tests**.
- AC-P1-007f satisfied via explicit close. No blocking fix, no scope.

## Criterion checks

- **AC-P1-007a (full re-run green):** PASS — see Re-run log (303 passed; ruff ×2 clean;
  compose exit 0 on ephemeral env).
- **AC-P1-007b (matrix done-states P1-001…P1-006):** CONFIRMED —
  P1-001 schema/redaction tests (66 tests, leak paths pinned) ✓;
  P1-002 source opens/closes cleanly (lifecycle + DI, cv2 confined to `capture.py`) ✓;
  P1-003 no unbounded backlog (drop-oldest, invariant under stress) ✓;
  P1-004 state transitions pass (strict-`>`, no-dup, pre-frame progression) ✓;
  P1-005 disconnect/reconnect pass (exact `[1,2,4,8,16,30,30]`, reset, honesty) ✓;
  P1-006 FPS/drop/reconnect metrics (exact fps, read-only, bounded) ✓.
- **AC-P1-007c (METHODOLOGY §7 + plan Build/Test/Exit + assembly answered):** PASS with
  the §1 caveat — Build (config/capture/queue/stall/reconnect/telemetry) all landed;
  Tests (invalid URL ✓ P1-001; disconnect/reconnect ✓ P1-002/004/005; corrupt-frame
  handling ✓ P1-002 read-failure paths; queue boundedness ✓ P1-003); Exit claimable as
  component-complete per §1.
- **AC-P1-007d (PROGRESS.md accurate):** VERIFIED — see PROGRESS-accuracy check.
- **AC-P1-007e (zero unresolved Critical/Important):** HOLDS — 0 Critical / 0 Important
  new; all carried items remain Minor/FYI (ledger below); both P1-001…P1-006 review
  chains ended APPROVE with zero open blockers.
- **AC-P1-007f (dual-keyword resolved):** CLOSED per §2.
- **AC-P1-007g (no Phase 2+ leakage; ledger reconciled):** PASS — leakage greps clean
  (only substring false positives: "exposed"/"composed"); `mqtt/__init__.py` is the
  P0-001 skeleton docstring, no implementation; deps exactly
  `pydantic×2 + opencv-python-headless + numpy`; compose untouched since P0-004.

## PROGRESS-accuracy check (pack `PROGRESS.md` vs repo)

- §1 status "Phase 1 IN PROGRESS (P1-006 complete)", current task P1-007: ACCURATE
  (HEAD `551728b` is the P1-006 commit; §5 shows P1-007 NOT STARTED — expected, this
  gate is the in-flight task).
- §2 "Phase 1 86% (6/7)": ACCURATE (6 of 7 matrix rows landed).
- §4 test counts re-verified by per-file collect at HEAD:
  camera 66 (75+66=141 ✓ P1-001), capture 24 (21+2+1 across P1-002/P1-003/fix ✓),
  queue 25 (190 ✓ P1-003), health 43 (233 ✓ P1-004), reconnect 31 (264 ✓ P1-005),
  telemetry 39 (303 ✓ P1-006); 75 P0 + 228 P1 = 303 = full-suite result ✓.
- §4 commit hashes `e676ec1/b9431db/1106a3c/5c3d18f/eef3f31/551728b`: match `git log` ✓.
- §8 verification rows (counts, fix-loop notes): consistent with reports + this re-run ✓.
- §12 per-task entries: match briefs/reports/reviews (incl. dual-keyword deferral-to-P1-007
  note in P1-005 entry — now resolved by §2 above) ✓.
- Sole inaccuracy: §3 stale Phase-0 template (FYI above; pack-side, out of scope).

## Open-items ledger (reconciled)

| # | Item | Prior state | Current state |
|---|---|---|---|
| 1 | MIT-license placeholder (`pyproject.toml` `license.text="MIT"`, no `LICENSE` file) | Open → P12 | OPEN → P12 (confirmed: `Test-Path LICENSE` False). No escalation. |
| 2 | P1-001: `model_copy(update=…)` validation bypass | Minor | Minor — no in-tree `model_copy` consumer (grep clean). |
| 3 | P1-001: `raise … from exc` cause-chain echo | Minor | Minor — `str(exc)` paths stay clean; no traceback-logging consumer in tree. |
| 4 | P1-001: unencoded-delimiter passwords → urlsplit wrong host | Minor (P1-002 handoff) | Minor — no network dialing exists in tree; dies with the future manager's URL handling. |
| 5 | P1-001 re-review: `__repr_args__/__pretty__`/devtools path | Minor | Minor — no devtools dependency; no pretty-print consumer (grep clean). |
| 6 | P1-001 re-review: `.errors()/.json()` structured echo | Minor | Minor — no in-tree serializer of structured errors (grep clean). |
| 7 | P1-002 minors ×4 (BaseException docs, threading note, `__exit__`, cleanup-swallow) | Closed in P1-003 + re-review | CLOSED — verified present in current `capture.py` (`:27-33,79-83,188-194,210-215`, cleanup comments `:137-139,150-152`). |
| 8 | P1-003 minors ×2 (stale bullet, arming-branch test) | Closed in re-review | CLOSED — bullet exact-scoped (`capture.py:10-14`); arming test at `test_capture.py:443-452`. |
| 9 | P1-004 M1: non-numeric thresholds → `TypeError` not `ValueError` | Minor | Minor — still present (`health.py:122`, no guard); no untyped construction path in tree (pydantic validates upstream). |
| 10 | P1-005 Minor-1: dual-keyword surface | Minor, deferred to this gate | CLOSED by §2 ruling (explicitly closed, pinned, harmless). |
| 11 | P1-005 Minor-2/3 (cap semantics doc, int-vs-float) | Closed in fix loop | CLOSED — verified (`reconnect.py:261-262`, `:139` `float(…)`). |
| 12 | P1-006 Minor-1: out-of-order notes bypass head-prefix prune; docstring overstates | Minor | Minor — still present (`telemetry.py:43-44` vs `:256`); fps unaffected (full-scan `:279`), memory capped (16384). Production (monotonic) path exact. |
| 13 | P0-006 logger minors (raw `record.name`, unguarded `json.dumps`) | Deferred to owning task | Still deferred — `logger.py` untouched since `3ac6763` (git log clean); telemetry logs nothing, so no interaction. |
| 14 | Assembly gap (this gate, §1) | — (new) | Minor → Phase 2 integration point (P2-004 precondition). |

No carried item escalated: every Minor remains Minor (no new caller/consumer in tree
touches the residual paths — verified by `model_copy/.errors()/devtools/rich` grep:
single hit is the `__rich_repr__` definition itself).

## Re-run log (full, at HEAD `551728b`)

| # | Command | Result |
|---|---|---|
| 1 | `pip install -e .` | PASS — `Successfully installed eldercare-vision-0.1.0` (plus env-only pip-update notice 25.3→26.2.1, FYI) |
| 2 | `ruff check .` | PASS — `All checks passed!` |
| 3 | `ruff format --check .` | PASS — `80 files already formatted` |
| 4 | `python -m pytest -v` | PASS — **303 passed in 0.64s** (expectation "303 passed" met exactly) |
| 5 | `python -m pytest --collect-only -q` | 303 collected (75 P0 + 228 Phase-1; per-file 66/24/25/43/31/39) |
| 6 | `docker compose config --quiet` (ephemeral env `POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB`, nothing to disk) | PASS exit 0. First attempt with incomplete env (missing USER/DB) failed on fail-closed `${VAR:?…}` interpolation — reviewer error, honestly recorded; re-run with full ephemeral env green. Confirms Phase 1 changed nothing infra-side (compose last touched `20dbd28`; deps stable since `b9431db`). |

## Re-verification note

Reviewer executed the suite (unlike prior read-only reviewers — this brief explicitly
permits read-only execution: pip install, ruff, pytest, compose config, greps, git).
All behavioral claims above re-verified independently: per-file test counts by collect,
dual-keyword signature by live `inspect`, leakage/confinement/no-consumer claims by
grep, HEAD/dirt state by git, module contracts by full static re-read of all six
stream modules. Prior reports' RED→GREEN narratives and reviewer probe claims were
cross-checked for internal consistency (arithmetic 75→141→162→190→233→264→303 holds
at every step) and no contradiction was found. No repo file was created or modified
except this review.

## Counts

- Critical: 0 | Important: 0 | Minor: 1 (new: assembly gap) + 9 carried-confirmed | FYI: 1 (new: PROGRESS §3 staleness) + carried
- Verdict: APPROVE — Phase 1 COMPLETE (component-complete; wired-ingest integration is a documented P2-004 precondition per §1).
