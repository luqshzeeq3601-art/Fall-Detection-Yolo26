# P3-001 — Configure ByteTrack: Reviewer Report

Reviewer: fresh review subagent (no prior context; implementer report treated as unverified claims).
Date (UTC): 2026-09-22. Working dir: `eldercare-vision/`. Env: `.venv\Scripts\python.exe` (Python 3.10.8, pytest 9.1.1). Ruff 0.16.8 isolated via `%TEMP%\ruff-p3001` (`PYTHONPATH` only, nothing installed into project venv).

## 1. Scope / snapshot

- Brief (binding): `docs/task-briefs/P3-001.md` (AC-P3-001a..g; `TrackObservation` reserved for P3-002; history/expiry later).
- Under review (all untracked-new except the deletion):
  - `src/eldercare/vision/tracking/tracker.py` (548 lines, read full)
  - `src/eldercare/vision/tracking/__init__.py` (23 lines, read full)
  - `tests/unit/test_pose_tracker.py` (450 lines, 27 tests, read full)
  - `tests/integration/test_tracked_pose_sequence.py` (118 lines, 3 tests, read full)
  - `docs/task-reports/P3-001.md` (implementer report, read full)
- Pack references checked: `AI_SPEC.md` §5 (ByteTrack default, `(camera_id, track_id)` history key), `CONSTRAINTS.md` §2 (`tracker: bytetrack.yaml`, `yolo26s-pose.pt`), `ARCHITECTURE.md` §§2–5 (Vision Worker owns tracking; Track observation interface listed — correctly NOT implemented here), `TASK_SKILL_MATRIX.md` P3-001 row (Ultralytics `yolo-inference`, done when track IDs produced).
- Git (fresh, from repo root): `git status --short` shows exactly ` D src/eldercare/vision/tracking/.gitkeep` + 6 untracked (`tracker.py`, `__init__.py`, 2 test files, brief, report). `git diff --stat -- eldercare-vision/src eldercare-vision/pyproject.toml eldercare-vision/tests` shows only the `.gitkeep` deletion (0 insertions/0 deletions). **Zero modified tracked files.** Allowed set matches brief §Files (2 src + 2 tests + brief + report + `.gitkeep` deletion).

## 2. Verification performed (fresh vs historical)

All executed fresh by this reviewer (exact outputs); nothing taken on trust from the report:

| # | Command (from `eldercare-vision/`) | Fresh output |
|---|---|---|
| 1 | `pytest tests/unit/test_pose_tracker.py tests/integration/test_tracked_pose_sequence.py -q` | `30 passed in 0.60s` |
| 2 | `pytest tests/unit/test_pose_tracker.py --collect-only -q` / integration | `27 tests` / `3 tests` (total 30, ≤ 30 per brief) |
| 3 | `pytest -q` (full) | `522 passed in 3.49s` (= 492 prior + 30 new; matches report's 522 claim) |
| 4 | `python -c "import ultralytics"` / `"import torch"` | `ModuleNotFoundError` both — confirms "absent here" record, production path unverified-live |
| 5 | ruff 0.16.8 isolated: `ruff check .` / `ruff format --check .` | `All checks passed!` / `121 files already formatted` |
| 6 | `git diff` on `pose/` + `pyproject.toml` | empty — zero Phase 2 diff, no dep changes |
| 7 | Live probes (see §4) | all pass (details below) |

Historical (implementer) claims checked: RED→GREEN narrative (§3 of report), command table (492 baseline → 522, ruff 0.16.8 isolated, `121 files already formatted`), lint history (10 errors fixed). These are consistent with the fresh state (e.g. ruff version and file count reproduce exactly); the RED state itself was not re-executed (source already exists) but the described failure mode (collection `ModuleNotFoundError` pre-implementation) is the only possible outcome given the imports, so it is judged credible.

## 3. AC-by-AC verdicts

- **AC-P3-001a (stock ByteTrack configured): PASS.** `ByteTrackConfig.tracker` defaults `"bytetrack.yaml"`, `persist=True` (`tracker.py:166-167`, tested `test_config_defaults_select_stock_bytetrack`). Grep for `thresh|max_age|match|buffer|conf_thres|iou_thresh|nms` in `tracking/` hits only docstring words ("thresholding"/"thresholds" in non-goal statements) — zero guessed tuning keys. Only `model.track` kwargs are `source/persist/tracker/verbose` (`tracker.py:400-405`).
- **AC-P3-001b (stable IDs): PASS.** First-frame, 3-frame stability, multi-person independence, zero-person-clean-with-backend-consulted, disappearance→`None`→reappearance passthrough — all covered by unit + integration tests and reproduced in live probe (scripted `(4,)/(None,)/(4,)` semantics asserted by `test_disappearance_none_reappearance_passthrough`).
- **AC-P3-001c (unassigned→None, fail-closed): PASS.** `None` passthrough; `None`/wrong-type frame, bad image (None/2-D/wrong dtype), count mismatch (`ValueError`), bad IDs (`True`→TypeError, `-1`→ValueError, `"3"`→TypeError, `2.5`→TypeError), backend exception propagation — all tested and live-probed (mismatch raises `ValueError: backend/detection count mismatch: 2 ids vs 1 detections (ref…)`).
- **AC-P3-001d (bit-exact preservation): PASS.** `update` zips input `pose.persons` objects directly into `TrackedPerson` (`tracker.py:531-534`); `test_persons_preserved_bit_exact_identity` asserts `is` identity, order, bbox/confs/keypoints. No threshold/filter/reorder code: grep for `sorted(|filter(|threshold|reorder|reverse` hits only docstrings.
- **AC-P3-001e (seam, no leakage): PASS.** `TrackBackend` Protocol (`tracker.py:174-188`); downstream types carry `int | None` only (`_check_track_id`, `tracker.py:91-101`, bools rejected); `__init__.py` exports exactly the 8 tracking names, no framework re-export. Triple framework-freedom proof in tests (sys.modules diff, fresh-interpreter subprocess, AST scan) passes fresh as part of the 30. Live: `PoseTracker()` default construction does NOT import ultralytics (`test_tracker_rejects_bad_backend_and_uses_lazy_default` asserts `"ultralytics" not in sys.modules`).
- **AC-P3-001f (bounded state, reset): PASS.** `PoseTracker` holds only `_config`/`_backend` — asserted by `test_tracker_holds_no_unbounded_state` and reproduced live (`vars: ['_backend', '_config']` across two updates). `reset()` delegates to backend if callable (`tracker.py:541-545`); production `reset()` drops cached model (`tracker.py:456-458`); camera-reconnect purpose documented (`tracker.py:27-31`). ByteTrack internals documented as backend-owned.
- **AC-P3-001g (CPU-only CI, gates): PASS.** 30 new (≤30), 522 full green, ruff check + format clean (fresh), zero Phase 2 diff, `pyproject.toml` untouched, no `ultralytics/torch/cv2` imports in tests (grep: no matches), no sleeps/GPU/network/download in `src` or executed tests (grep for `sleep|download|requests|urllib|socket|cuda` in `tracking/`: only docstring/runtime-assumption mentions + the single lazy `from ultralytics import YOLO` at `tracker.py:394` inside `track()`).

## 4. Reviewer-critical checks a–g (+ live probes)

a. **IDs from tracker, not synthetic counters: CONFIRMED.** `PoseTracker.update` returns `self._backend.track(...)` entries verbatim after `_check_track_id` validation (type/range check only, no generation). Grep `counter|next_id|_next|uuid|random\.|id_generator` → single hit: `enumerate(flat_ids)` at `tracker.py:442`, used solely as error-message index. Live probe: `vars(tracker)` after updates = `{'_config','_backend'}` — no counter/ID state. Scripts `(None,)`, `(0,)`, `(5,)` each pass through exactly (incl. falsy `0`/`None` — no `or`-default fabrication). Fakes (`ScriptedBackend`, `_BoomBackend`, `_Backend`) implement only the `track(detections, image)` surface with canned tuples — test doubles, not production logic (production path is the separate `UltralyticsByteTrackBackend` class, never executed here).

b. **Pose contract preserved: CONFIRMED.** Output persons ARE input objects (`is` asserted), order kept via `zip(..., strict=True)`, bbox/keypoints/confs asserted bit-exact. No threshold/filter/reorder code anywhere in `tracking/` (grep hits are docstring non-goal statements only).

c. **Association rule sound: CONFIRMED.** Greedy-IoU documented in module docstring (`tracker.py:15-21`) + helper docstring (`tracker.py:226-231`) + report §5. Tested: matched pairs, unmatched→`None`, surplus ignored, claimed-once, empty inputs, known IoU values (1.0/0.0/1/3/degenerate-0.0). Live probe: `associate(((0,0,10,10),), ((0,0,10,10),(50,50,60,60)), (7,8)) == (7,)` (surplus ignored); disjoint detection → `(None,)`. Judgment: count mismatch between **backend and boundary** fails closed (`ValueError`, `tracker.py:525-530`); mismatch between **tracker-internal boxes/ids** also fails closed (`tracker.py:235-239`, `436-441`). There is NO silent-misalignment path — every length disagreement raises; every IoU non-overlap degrades to `None` explicitly. Correct choice.

d. **Production backend honesty: CONFIRMED.** Single `from ultralytics import YOLO` at `tracker.py:394`, inside `track()` method body — proven by AST test (exactly `[("ultralytics", True, "from")]`, no module-level framework imports). Stock `bytetrack.yaml` only; grep for tuning keys finds none. Unverified-live assumptions explicitly recorded (`tracker.py:36-50`, report §6): one-element Results list, `boxes.id`/`boxes.xyxy` pairing, `None`-means-unassigned, integral-float normalization. `torch`/`ultralytics` absent confirmed fresh (`ModuleNotFoundError` both). **Loud failure confirmed live:** default-backend `update()` raises `ModuleNotFoundError: No module named 'ultralytics'` — no silent fallback, no fabricated tracks, no swallowed exception (fail-closed `ValueError` on empty results list, `tracker.py:406-409`).

e. **State bounded: CONFIRMED** (see AC-f). `reset()` contract tested (`test_reset_contract`: delegates, `resets == 1`, tracker usable after). Backend ownership documented (`tracker.py:476-477`, `502-504`).

f. **No leakage: CONFIRMED.** `TrackedPerson.track_id: int | None` validated (`None`/non-negative int, bools rejected); `TrackedFrame` dims validated; frozen dataclasses; no framework objects in signatures. `__init__.py` clean (8 names).

g. **Scope: CONFIRMED.** `class/def TrackObservation` grep → no matches (single mention is the "What is NOT here" docstring, `tracker.py:33-34`). No history/expiry/fall/FSM/alert/dataset/training/export/MQTT/DB/frontend/benchmark identifiers in `tracking/` beyond non-goal docstrings. `git diff` proves `pose/` (adapter/inference/pipeline/timing), `pyproject.toml`, existing tests, scripts, config untouched. CPU-safe: no GPU/network/download/sleep in `src` or executed tests.

## 5. Mutation / spot probes (fresh, exact)

1. Passthrough-exact: backend `(None,)`→`None`, `(0,)`→`0`, `(5,)`→`5` — OK (falsy IDs not defaulted).
2. `vars(PoseTracker)` after 2 updates = `['_backend', '_config']` — OK.
3. Count mismatch `(1,2)` vs 1 person → `ValueError: backend/detection count mismatch…` — OK (fails closed, not silent).
4. Surplus tracks ignored → `(7,)`; disjoint → `(None,)` — OK.
5. Default backend without ultralytics → `ModuleNotFoundError` (loud) — OK.
6. Test-file forbidden-import grep (`ultralytics|torch|cv2|sleep|download|GPU|cuda`) → no matches both files — OK.

## 6. Findings

**Critical: none. Important: none. Minor: none.**

- FYI-1 — Report says "`tracker.py` (new, ~560 lines)"; actual file is 548 lines. Approximation only; no action.
- FYI-2 — `TrackedFrame.__post_init__` tolerates `list` input by coercing to tuple (`tracker.py:292`). Lenient-input nicety, consistent with frozen-output semantics; not a scope or contract violation.
- FYI-3 — Implementer's RED evidence (intermediate 29-pass/1-fail from own test-script bug) is plausible and self-disclosed in report §3; fresh GREEN state (30 passed) verified. No action.

## 7. Final verdict

**APPROVE.** All AC-P3-001a..g pass on fresh execution (30 new + 522 full + ruff check + ruff format clean), all reviewer-critical checks a–g confirmed with live probes, git footprint exactly as allowed with zero modified tracked files, no Critical/Important findings. No scoped fix required. Do NOT start P3-002 (out of scope for this review).
