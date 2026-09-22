# P3-005 Review — Multi-person / occlusion tracking validation (TEST-ONLY)

**Verdict: APPROVE** — 0 Critical, 0 Important, 2 Minor, 0 FYI. No fix loop required.

## 1. Scope / snapshot

- Task: P3-005, TEST-ONLY. Binding brief: `docs/task-briefs/P3-005.md` (AC-P3-005a..h, ≤30-test cap, duplication-bloat rule, zero `src/` diff).
- Files under review (all new, all untracked):
  - `tests/unit/test_multi_person_isolation.py` (18 tests)
  - `tests/integration/test_occlusion_sequences.py` (6 tests)
  - `docs/task-briefs/P3-005.md` (brief, pre-existing untracked)
  - `docs/task-reports/P3-005.md` (implementer report)
- Pack row: `TASK_SKILL_MATRIX.md` P3-005 — Ultralytics `yolo-inference`, TEST+VISION, done when no state leakage.
- HEAD at review time: `49945f9` (P3-004 close). No isolation defect was claimed; none found by this reviewer either.

## 2. Verification (fresh, by this reviewer)

| Check | Result (fresh) |
|---|---|
| Focused pytest (2 new files) | **24 passed in 0.29s** (exact output: `24 passed in 0.29s`) |
| Full pytest | **626 passed in 2.84s** (exact output: `626 passed in 2.84s`) = 602 prior + 24 new |
| Collect-only | 24 tests collected (18 unit + 6 integration) |
| Git footprint | `git status --porcelain` shows ONLY the 4 untracked paths above; `git diff --stat`, `git diff --stat -- eldercare-vision/src/`, `git diff --name-only` all **empty** → zero modified tracked files, zero production diff |
| Ruff | **Historical-carry**: `.venv\Scripts\python.exe -m ruff --version` → `No module named ruff`. Installs are outside reviewer scope, so ruff was NOT re-run. Carried from implementer report: `ruff check .` → All checks passed; `ruff format --check .` → 141 files formatted (after formatting the 2 new files). Reason recorded; no evidence of lint failure, but not freshly proven. |

## 3. AC-by-AC verdicts

- **AC-P3-005a** (simultaneous histories bit-exact; crossing without merge/swap): **PASS** — unit `test_two_people_simultaneous_histories_independent_bit_exact`, `test_crossing_close_approach_histories_follow_backend_ids`; integration `test_cross_gap_reorder_chain_end_to_end` frames 0–1.
- **AC-P3-005b** (gap semantics: same-ID continues, different-ID forks, survivor uninterrupted, no fabrication): **PASS** — unit disappearance / same-ID / different-ID tests; integration `test_gap_fork_chain_end_to_end`. Reviewer's own gap-fork probe confirmed old key byte-identical post-gap, new key length 1.
- **AC-P3-005c** (`None` never contaminates; cross-camera isolation both directions): **PASS** — unit `test_none_ids_never_contaminate_histories` (production `history.py:157-159` drops `None`; test appends all observations, no test-side filtering) and `test_same_numeric_id_across_cameras_isolated_both_directions`; integration `test_cross_camera_same_ids_chain_end_to_end`, `test_none_mix_and_zero_person_chain_end_to_end`. Reviewer's own camera probe confirmed both directions.
- **AC-P3-005d** (order swaps prove position-independence; gap returns land only in named key): **PASS** — unit 2-frame swap + 3-frame adversarial reverse/rotation + `test_tracker_index_wise_pairing_ignores_list_position`; unit `test_gap_return_lands_only_in_backend_named_key`; integration chain frame 3 reorder. See §4b for discrimination analysis.
- **AC-P3-005e** (expiry affects only intended key; zero-person preserves state; determinism): **PASS** — unit expiry + zero-person + determinism tests; integration `test_full_sequence_determinism_end_to_end`.
- **AC-P3-005f** (per-entry content incl. 0.0/tiny/missing; end-to-end chain): **PASS** — unit content-attachment + missing-keypoint tests; integration `test_cross_gap_reorder_chain_end_to_end` (5 frames, expire pass, per-key snapshots + timestamps).
- **AC-P3-005g** (≤30 tests, isolation-justified; CPU-only): **PASS** — 24 tests; no framework imports at runtime (probed: `torch`/`ultralytics` absent from `sys.modules`); zero sleeps; synthetic inline fixtures. See §4f for bloat judgment.
- **AC-P3-005h** (ruff + pytest green; 602 prior unmodified; zero production diff; no dep changes): **PASS with ruff-carry** — pytest fresh-green (626), git footprint clean, no dep changes; ruff carried as historical (see §2).

## 4. REVIEWER-CRITICAL checks a–h

**a. Zero state leakage (own probes).** PASS. Probe 1 (2-person swap `[(1,2),(2,1)]` across `[A,B]→[B2,A2]`): key 1 = `[A,A2]`, key 2 = `[B,B2]` — no swap, no merge. Probe 2 (gap fork `[(1,),(1,),(),(9,)]`): old key tuple-identical pre/post gap (`True`), new key length 1 with timestamp `[3.0]`. Both match suite results.

**b. Identity never depends on list position (discrimination analysis).** PASS — genuinely position-discriminating. Production pairing path is `tracker.py:506-539` (`PoseTracker.update`): index-wise `zip(pose.persons, track_ids, strict=True)` into `TrackedPerson(person=person, track_id=...)`; persons are never sorted. Counterfactual: if production sorted persons by bbox, `test_order_swap_two_frames_identity_follows_ids` (frame 2 `(B2,A2)` + script `(2,1)`) would pair A2→2/B2→1 and the `snap_1 == [A,A2]` assertion would FAIL. Likewise `test_tracker_index_wise_pairing_ignores_list_position` (script `(2,1)` on `[left,right]`, asserting `persons[0].track_id == 2` with `is`-identity) would fail under ID-sorting. The adversarial 3-frame reverse+rotation test extends this to 3 keys. These tests would catch position-dependence, not merely pass alongside it.

**c. Camera namespace isolation both directions.** PASS. Unit test drives two independent trackers (ids `(5,)` each) into one shared history and asserts both snapshots, both `camera_id` fields, and exact key ordering `(("cam-a",5),("cam-b",5))`. Reviewer's own probe confirmed cam-a key holds only A content and cam-b key only B content. Integration chain repeats the pattern end to end.

**d. Occlusion follows backend IDs exactly.** PASS. Same-ID return continues a single key with timestamp jump (`[0.0, 3.0]`, unit + integration); different-ID return forks fresh while the old key stays tuple-identical (reviewer probe: `True`). Post-gap observations land only in the backend-named key with the sibling key frozen (`frozen_a + (returned[0],)` / `frozen_b + (returned[1],)`). No reappearance-ID policy is guessed — all ID sequences are scripted backend returns.

**e. No synthetic identity guessing in the new tests.** PASS. Both `ScriptedBackend` fakes replay programmed ID tuples verbatim (`track` returns `self._scripts[calls-1]`); every test programs the backend first and asserts OUR layer follows it. The `_drive` helper appends every returned observation (including `None`-carrying ones) — `None` exclusion happens in production `history.py:157-159`, not by test-side filtering. No test asserts any real-ByteTrack occlusion behavior.

**f. Duplication-bloat judgment (per brief).** PASS — no Important-bloat. Every test requires ≥2 keys, ≥2 frames, ≥2 cameras, or a gap/reorder/`None` mix; the report's non-duplication statement names the excluded single-key coverage (append order, eviction internals, strict-`>` boundaries, idempotency, converter validation, config validation, greedy-IoU). Borderline candidates judged: the two determinism tests are brief area 12 (required); the three framework-freedom tests are the brief-mandated `sys.modules`+AST proofs (unit splits runtime/AST, integration covers its own module — acceptable, not bloat). No test merely re-asserts single-key P3-001…P3-004 coverage. Total 24 ≤ 30 cap.

**g. AST/sys.modules freedom real, not vacuous.** PASS. Unit `test_ast_no_framework_imports` asserts non-empty scans for observation.py/history.py (`unit:481`) and tracker.py module-level roots (`unit:492`); the tracker module-level-only scoping correctly defers to the P3-001-pinned lazy method-level `ultralytics` import (cited by test name in comment). Unit `test_runtime_free_of_frameworks` diffs `sys.modules` and additionally asserts global absence of `torch`/`ultralytics`. Integration `test_runtime_and_ast_freedom` lacks the non-empty guard (see Minor-2) but is non-vacuous in fact: reviewer counted 10 import roots (`__future__, ast, eldercare, numpy, pathlib, sys, typing`) in the integration module today.

**h. The two tester-raised nits — ratings.**
- **Nit (1) — unit:388 `assert tiny[0] == 0.0`: Minor.** The assertion compares two in-test literals (`tiny[0]` is `0.0` by construction at unit:374) and proves nothing about production; 4 of 5 `tiny` elements are never used. Harmless because the surrounding assertions (unit:382-387: detection confidences `0.0`/`1.0`, per-keypoint confs, bboxes) genuinely pin content attachment — the line adds no false confidence and no test-count inflation. Suggested cleanup (delete line + unused list), NOT required. **No fix loop.**
- **Nit (2) — integration:224 freedom test missing non-empty guard: Minor.** The AST scan would pass vacuously if the module ever had zero imports, since `[]` contains no forbidden roots. In fact the scan is real today (10 roots counted by reviewer), so no coverage is lost; this is future-robustness only. Suggested one-line guard (`assert roots, ...`), NOT required. **No fix loop.**
- Fix-loop rule (Critical/Important only): neither nit triggers it.

## 5. Probes (all fresh, all PASS)

1. 2-person swap probe: key1 bboxes `[(10.0,20.0,60.0,120.0), (14.0,22.0,64.0,122.0)]`, key2 `[(200.0,100.0,300.0,250.0), (204.0,102.0,304.0,252.0)]` — OK.
2. Gap-fork probe: old key byte-identical `True`, new key `len 1`, timestamps `[3.0]` — OK.
3. Camera both-directions probe: cam-a key `[A]`, cam-b key `[B]`, `camera_id` fields correct — OK.
4. Import-root counts: unit 10 roots, integration 10 roots — scans non-vacuous — OK.

## 6. Counts

- New tests: 18 unit + 6 integration = **24 total (≤30 cap)**.
- Full suite: **626 passed** (602 prior unmodified + 24 new).
- Test-command outputs: focused `24 passed in 0.29s`; full `626 passed in 2.84s`; collect `24 tests collected`.

## 7. Findings

### Critical — 0

None.

### Important — 0

None. (Explicit duplication-bloat sweep per §4f: no test flagged.)

### Minor — 2

1. **Minor-1 — tautological literal assertion** (`tests/unit/test_multi_person_isolation.py:388`): `assert tiny[0] == 0.0` asserts an in-test literal (`tiny` defined `unit:374` as `[0.0, 1e-6, 1e-3, 0.5, 1.0]`); 4 of 5 elements unused. Evidence: the line cannot fail regardless of production behavior. Harmless (real pinning at lines 382-387 stands). Suggested: delete the line and the `tiny` list. Not required; no fix loop.
2. **Minor-2 — freedom test lacks vacuous-scan guard** (`tests/integration/test_occlusion_sequences.py:224-239`): `test_runtime_and_ast_freedom` asserts `not [...forbidden...]` without first asserting the scanned `roots` list is non-empty (contrast unit:481/492 guards). Evidence: reviewer counted 10 roots in the module today, so the check is real — the gap is future-robustness only. Suggested: add `assert roots, ...`. Not required; no fix loop.

### FYI — 0

None.

## 8. Final verdict

**APPROVE.** All AC-P3-005a..h pass (h with explicit ruff historical-carry). Zero production diff, zero modified tracked files, 24/30 tests, 626 green. No Critical/Important findings; the two Minor nits require no fix loop. No scoped fix issued. Do NOT start P3-006 (coordinator owns sequencing).
