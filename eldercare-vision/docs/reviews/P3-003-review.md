# P3-003 Review — Bounded per-track history

Reviewer: fresh reviewer (no prior context; implementer report treated as unverified).
Date (UTC): 2026-09-22. Working directory: `eldercare-vision/`.
Verdict: **APPROVE** — 0 Critical, 0 Important findings.

## 1. Scope / snapshot reviewed

- `src/eldercare/vision/tracking/history.py` (new, 194 lines: `TrackHistoryConfig` + `TrackHistory`)
- `src/eldercare/vision/tracking/__init__.py` (additive-only re-export diff: 1 import line + 2 `__all__` entries)
- `tests/unit/test_track_history.py` (new, 25 tests)
- `tests/integration/test_track_history_sequence.py` (new, 2 tests)
- `docs/task-briefs/P3-003.md` + `docs/task-reports/P3-003.md` (read as claims only)

Binding brief AC: AC-P3-003a..g. Forbidden scope respected (no expiry, no temporal
computation, no locks, stdlib-only imports in `src`, no other `src/` edits).

## 2. Verification performed (fresh, not historical)

All commands from `eldercare-vision/` with `.venv\Scripts\python.exe`:

| Check | Fresh output |
|---|---|
| Focused pytest (2 new files) | `27 passed in 0.26s` |
| Full pytest | `577 passed in 3.73s` (577 = 550 prior + 27 new; prior count per report baseline, see §3) |
| Unit collect-only | 25 tests; integration file holds 2 tests → 27 total, ≤ 30 cap |
| `ruff check .` (isolated reuse `$env:TEMP\ruff-p3003\bin\ruff.exe`, **no install**) | `All checks passed!`, version `ruff 0.16.8` |
| `ruff format --check .` (same binary) | `133 files already formatted` (report claimed 132 — see FYI-1) |
| Git footprint (from repo root) | 1 modified tracked file (`tracking/__init__.py`, +3 additive lines); untracked: `history.py`, 2 test files, brief, report. Zero other modified tracked files. `pyproject.toml`, `tracker.py`, `observation.py`, existing tests, scripts, config untouched. |
| Reviewer probe script (`TEMP/opencode/p3-003-review-probes.py`, 39 assertions) | 31/39 direct pass; 8 keyword-scan misses proven docstring-only by AST identifier dump + grep (see check g) |

## 3. AC-by-AC verdicts

- **AC-P3-003a (key `(camera_id, track_id)`; `None` ignored, explicit): PASS.** Key
  constructed as `(obs.camera_id, track_id)` (`history.py:142`); `None` early-returns
  (`history.py:140-141`), documented in module docstring (`history.py:9-14`), tested
  (`test_none_track_id_ignored_others_untouched`). Multi-track / multi-camera isolation
  tested and re-probed (check c, all PASS).
- **AC-P3-003b (fixed max; oldest-first eviction; truly bounded): PASS.** Per-key
  `deque(maxlen=self._config.max_observations)` (`history.py:145`); boundary N/N+1 tests
  assert full tuple equality; reviewer probe: `buf.maxlen == 4 == config`, 3×-max fill
  (15 appends, max 5) → internal len 5 with exact timestamps `[10..14]`. See check a
  judgment on key-set growth (FYI-2, not a defect).
- **AC-P3-003c (per-key ordering; duplicates arrival-ordered; OOO fail-closed,
  store unchanged; cross-key independence): PASS.** `timestamp >= last` appended,
  `< last` → `ValueError` naming key + both stamps (`history.py:147-155`), raised
  before `buffer.append` so store unchanged. Probed: duplicate bboxes return in arrival
  order; OOO message names key and both stamps; snapshot identical before/after;
  per-key comparison only (cross-key independence probed).
- **AC-P3-003d (fresh-tuple snapshots; unknown → `()`; deterministic remove/clear;
  no external mutation): PASS.** `snapshot` returns `tuple(buffer)` fresh object
  (`history.py:163`); `remove` bool via `pop(key, None)` (`history.py:172`); `clear`
  deterministic. Probed: `s1 == s2 and s1 is not s2`; tuple item assignment raises
  `TypeError`; `TrackObservation` is frozen (`FrozenInstanceError` on attribute set);
  store intact afterwards.
- **AC-P3-003e (no temporal/expiry/threshold; single-owner, no locks): PASS.**
  AST identifier dump over `history.py` shows only store/key/validation names
  (`append/clear/snapshot/keys/remove`, `timestamp` comparison, `deque/dict`) — zero
  velocity/angle/smoothing/score/FSM/expiry/TTL/lock/thread identifiers. All 18 grep
  keyword hits are docstring prose (contract + "What is NOT here" + single-owner note)
  or the legitimate `timestamp` ordering comparison. Single-owner documented
  (`history.py:42-45`), no locking primitives.
- **AC-P3-003f (≤ 30 tests; CPU-only; no framework imports; non-duplication):
  PASS.** 27 new tests; zero sleeps; hand-built observations + scripted backend;
  import scan of both test files + `history.py` shows no `torch/ultralytics/cv2`
  (integration test imports `numpy` only for the zero-image fixture — allowed, not
  forbidden); `sys.modules` probe introduced zero new modules. Report's
  non-duplication statement verified by inspection: tests assert only the store
  contract + wiring, no converter/schema/backend internals.
- **AC-P3-003g (ruff + pytest green; additive-only diff; no dep changes): PASS.**
  Fresh outputs in §2; `git diff` is exactly the 3-line additive `__init__.py` hunk;
  no dependency changes.

## 4. Reviewer-critical checks a–h

- **a. Truly bounded: PASS.** `deque.maxlen == config.max_observations` (probed, max 4);
  3×-max fill → len == max with exact expected tuple; instance state is exactly
  `{_config, _buffers}` of `maxlen` deques, no lists. **Key-set judgment (FYI-2):**
  dict-key count grows with *distinct* `(camera_id, track_id)` identities until
  `remove()`/`clear()`/P3-004 expiry — this is inherent to any keyed store and the
  brief itself defines bound semantics as `(#keys) × max_observations` while assigning
  time-based expiry to P3-004 (forbidden scope here). Adding key eviction now would
  violate forbidden scope. **Not a defect.**
- **b. Eviction/order deterministic: PASS.** Exact-tuple (not length-only) boundary
  probes at N and N+1; duplicates distinguished by bbox returned in arrival order;
  OOO raises `ValueError` naming key + both stamps with snapshot byte-identical after.
- **c. No cross-track/cross-camera contamination: PASS.** Probed: per-key timestamp
  sequences and key set exactly as scripted; no leakage across tracks or cameras.
- **d. None-track asymmetry: judged SOUND (no finding).** Append ignores `None`
  (live-loop-friendly, brief-mandated, documented + tested); `snapshot`/`remove`
  reject `None` with `TypeError` (fail-closed key validation, brief-mandated).
  Rationale: `None` is an append-time condition, never a valid stored key, so lookup
  APIs treat it as caller bug. Consistent with brief + report assumption.
- **e. No external mutation: PASS.** Fresh tuples (`is not`), tuple immutability,
  frozen observations (reviewer attempted mutation → `FrozenInstanceError`), store
  intact. Snapshots share observation *references*, which is safe precisely because
  `TrackObservation` is frozen (verified, not assumed).
- **f. Default 60 rationale: judged SOUND.** Engineering default tied to AI_SPEC §9
  `history_seconds: 2.0` at 15–30 fps (≈30–60 obs), documented as non-calibrated in
  the `TrackHistoryConfig` docstring (`history.py:94-105`). Capacity, not semantics;
  configurable per store.
- **g. No forbidden code / no framework leakage / no duplication: PASS.** Per §3,
  AC-P3-003e + AC-P3-003f evidence above. AST import roots in `history.py`:
  `__future__, collections, dataclasses, typing, eldercare` only.
- **h. Consumer integration uses store+observation APIs only: PASS.** Integration
  consumer blocks (`test_track_history_sequence.py:101-115, 127-131`) read only
  `history.snapshot/keys/len` + `obs.timestamp/track_id/camera_id/bbox_xyxy`;
  `PoseTracker`/scripted backend/converter appear solely in the frame-producing setup
  path the brief explicitly allows. No history-policy logic outside the store.

## 5. Findings

**Critical: none. Important: none. Minor: none.**

- **FYI-1:** `ruff format --check .` reports `133 files already formatted` vs the
  report's `132`. Same isolated binary (`0.16.8`), gate passes either way
  (exit 0, nothing to reformat). Likely transcription drift; no action.
- **FYI-2:** Key-set growth with distinct track identities is P3-004's expiry
  scope by design (see check a judgment). Confirm P3-004 bounds key lifetime; no
  action in this task.

## 6. Final verdict

**APPROVE.** All AC-P3-003a..g verified with fresh execution; git footprint is
exactly the allowed set with an additive-only `__init__.py` diff; no unresolved
Critical/Important findings; no scoped fix required. P3-004 may proceed.
