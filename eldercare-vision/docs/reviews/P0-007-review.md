# P0-007 Review — CI baseline (fresh security/code review)

- Task: P0-007 CI baseline (`docs/task-briefs/P0-007.md`, criteria a–f, forbidden scope)
- Spec: pack `AGENTS.md` §§11, 12 (security + git rules) + `TEST_STRATEGY.md` §5 (required CI checks)
- Evidence: `docs/task-reports/P0-007.md` + independent tester verdict PASS (file claims confirmed; d/f accepted on report evidence at matching HEAD)
- Target (working-tree, read-only; git HEAD `3ac6763`): `.github/workflows/ci.yml` (new, 90 lines)
- Reviewer method: read-only. No files modified, no gates re-executed in-tree (to avoid
  polluting the working tree). Full reads of `ci.yml`, the brief, the implementer report,
  pack `AGENTS.md` §§11–13 + `TEST_STRATEGY.md` §5, `frontend/package.json`,
  `pyproject.toml`, plus read-only checks: `git rev-parse`/`log`/`status --short`,
  `git diff --stat` (empty), `python -c yaml.safe_load` parse, `Select-String` scan for
  `continue-on-error` / `|| true` / `secrets.` / `docker` / `gpu` / `main:` / `services:` /
  `branches:` (no matches), `requirements*.txt` glob (none), `alembic.ini`/`migrations`/
  scan-config search (none), `package-lock.json` presence, and `git check-ignore frontend/dist`.

## Verdict: APPROVE

All acceptance criteria a–f are met as specified, security posture is minimal and clean,
and failure semantics are fail-closed. One Important follow-up (I1) is owned by the
coordinator, not the implementer: it is a gap in the brief's prescribed step list
(runner tooling), is fail-closed rather than a silent bypass, and needs a brief
amendment plus first-live-run observation — not a rework of this deliverable.
One Minor hardening item and four FYIs below are non-blockers.

## Findings

### Important I1 — python job invokes `ruff`/`pytest` without installing them; first live run likely red at "Ruff lint"

- Location: `.github/workflows/ci.yml:49-59` (`pip install -e .` → `ruff check .` →
  `ruff format --check .` → `pytest -v`); contrast `pyproject.toml:7-10`
  (runtime dependencies are only `pydantic`/`pydantic-settings`; no dev extras) and
  the empty `requirements*.txt` glob (no requirements files anywhere on disk).
- Issue: `actions/setup-python` provides an interpreter, not project tooling, and
  stock `ubuntu-latest` runners do not ship `ruff` (nor is a `pytest` console script
  guaranteed on the setup-python PATH). `pip install -e .` therefore does not place
  `ruff`/`pytest` on PATH. The local rehearsal was green only because the dev machine
  has ruff 0.16.6 / pytest 9.1.1 ambiently installed (report §rehearsal env line).
  The probable first-live-run outcome is `ruff: command not found` (exit 127) — a red
  baseline for environmental reasons, not gate reasons.
- Why not Critical: failure direction is fail-closed (the job fails loudly; no gate
  can pass silently), and the implementer is brief-compliant — the brief (§Requirements,
  python job) prescribes exactly this step list with no tool-install step, so the fix
  requires a coordinator brief amendment (e.g. an explicit `pip install ruff pytest`
  step with pinned versions), not implementer rework. The frontend job has no such gap
  (`npm ci` installs its devDependencies, including vitest/eslint/typescript).
- Suggested follow-up (coordinator, post-merge or brief amendment): watch the first
  real workflow run; if red with command-not-found, amend with a pinned tool-install
  step. Do not weaken any gate to get green.

### Minor M1 — no `timeout-minutes`; a hung job holds the runner up to the 6h default

- Location: `.github/workflows/ci.yml:37-61` (`python` job), `:61-90` (`frontend` job) —
  neither job sets `timeout-minutes`.
- Analysis: the brief does not require timeouts, so this is not a criterion miss, and
  the expected runs are short (report rehearsal: pytest 0.24s, build 173ms). A hung
  step (network stall in `pip install`/`npm ci`) would burn runner minutes and delay
  the red/green signal, but cannot produce a false pass. Cheap additive hardening for
  the coordinator (e.g. `timeout-minutes: 10–15` per job); no gate semantics change.

### FYI F1 — action tag pins, not SHA pins: compliant, weaker than maximum

- `ci.yml:41` (`actions/checkout@v4.2.2`), `:44` (`actions/setup-python@v5.3.0`),
  `:71` (`actions/setup-node@v4.1.0`): first-party `actions/*` only, all full semver,
  never floating majors — exactly what AC-P0-007c requires. Note only: mutable tags
  are trust-on-tag; SHA pinning would be stronger but is out of brief scope. No change requested.

### FYI F2 — `npm test -- --run` (→ `vitest run --run`) is a redundant but proven-harmless flag

- `ci.yml:87` vs `frontend/package.json:11` (`"test": "vitest run"`, already
  run-once/non-watch). The extra `--run` is belt-and-braces explicitness per the brief;
  the report records both bare and flagged invocations exiting 0 under vitest 5.0.1,
  and the `test` script itself is byte-identical (no script edit, per the brief's
  constraint). No change requested.

### FYI F3 — `pip` cache likely a silent no-op: harmless

- `ci.yml:47` (`cache: pip`) with no `cache-dependency-path` and no
  `requirements*.txt` on disk: `setup-python`'s pip cache keys off requirements files
  by default, so with a `pyproject`-only install it most likely warns and skips
  caching each run. Harmless (a missed speedup, not a correctness or poisoning issue);
  the brief mandates `cache: pip` verbatim. Optionally set
  `cache-dependency-path: pyproject.toml` in a later touch-up. No change requested.

### FYI F4 — YAML `on:` parses as boolean `True` under PyYAML: universal quirk, not a defect

- Independent `yaml.safe_load` parse succeeds; top-level keys are
  `['name', True, 'permissions', 'concurrency', 'jobs']` with
  `on == {'push': None, 'pull_request': None}` (both null-args = unfiltered) and
  `jobs == ['python', 'frontend']`. The `True` key is the well-known YAML 1.1
  `on`→boolean coercion in PyYAML; GitHub's own parser handles `on:` correctly and
  every Actions workflow exhibits this. AC-P0-007a holds. No change requested.

## Verified sound (no finding)

- **Triggers master-safe**: `push` + `pull_request` with no branch filter
  (`ci.yml:23-25`), with the `master`-vs-`main` rationale documented in the file
  comment (`:1-6`). No `main:`/`branches:` filter (grep-verified independently).
- **Minimal permissions**: `permissions: contents: read` top-level (`:28-29`); nothing
  in either job writes (no publish/deploy, no cache-write beyond the setup actions'
  scoped caches).
- **Concurrency sane**: `group: ${{ github.workflow }}-${{ github.ref }}`,
  `cancel-in-progress: true` (`:32-34`) — the brief-mandated standard group; latest
  push per ref wins. (Side effect, intended: superseded pushes to `master` also
  cancel, not just PR runs.)
- **Versions justified**: Python `3.10` ↔ local 3.10.11 major +
  `pyproject.toml:5` (`requires-python = ">=3.10"`) + `:20` (ruff `target-version =
  "py310"`); Node `24` ↔ local v24.14.1. Reasons recorded in-file (`:12-15`) and report.
- **Gate coverage matches repo files**: python `pip install -e .` → `ruff check .` →
  `ruff format --check .` → `pytest -v` (`:49-59`) mirrors `pyproject.toml` gates;
  frontend `npm ci` → `typecheck` → `lint` → `test` → `build` (`:77-90`) matches
  `frontend/package.json:6-12` verbatim (`typecheck`, `lint`, `test` = `vitest run`,
  `build` all present; `package-lock.json` present so `npm ci` is valid).
- **Working-directory correctness**: frontend `defaults.run.working-directory: frontend`
  (`:63-65`) covers all `run:` steps, while `cache-dependency-path:
  frontend/package-lock.json` (`:75`) is correctly root-relative — `defaults.run`
  does not affect action inputs, and the report documents exactly this. Python job
  runs at root, which `pip install -e .` requires. No silent wrong-directory path.
- **Failure semantics fail-closed**: independently grep-clean for `continue-on-error`,
  `|| true`, `secrets.`, `docker`, `gpu`, `services:`; stock ubuntu runners execute
  `run:` steps under `bash -e`, so any gate's non-zero exit fails its job. The report's
  failure-fails proof (scratch outside the repo, forced `assert 1 == 2` → pytest exit 1;
  unused-import → ruff exit 1, scratch deleted) is the honest local proxy the brief ordered.
- **TEST_STRATEGY §5 mapping justified**: Ruff ✓, pytest ✓ (no GPU-marked tests exist —
  only `@pytest.mark.parametrize` in `tests/unit/`), frontend lint/typecheck/test ✓.
  Migration validation and secret-scan/audit are "if configured" items; no
  `alembic.ini`/`migrations/`/scan config exists on disk, so inventing CI steps for
  them would have been scope fabrication. GPU/video benchmarks correctly stay local.
- **Third-party trust minimal**: only first-party `actions/checkout`, `setup-python`,
  `setup-node`; no custom/unknown actions; no services/containers/GPU labels/datasets;
  the sole `${{ }}` interpolation is the concurrency group (no injection into `run:`).
- **Hygiene / scope leakage**: `git diff --stat` empty (no tracked-file modification);
  `git status --short` shows only untracked `.github/`, the coordinator-supplied brief,
  and the report — i.e. the only deliverable is the new `ci.yml` plus its report.
  HEAD `3ac6763` matches the brief's P0-006 dependency. `frontend/dist/` is
  gitignored (check-ignore confirmed). No secrets committed; AGENTS.md §11 clean.
- **Report completeness**: workflow design table, pin table, 9-step rehearsal log at
  current HEAD, failure-proof log with exit codes, grep proofs, assumptions, and an
  explicit honest caveat that live GitHub execution is unverifiable from here — all
  present. No benchmark numbers or service APIs invented (AGENTS.md §14 clean).

## Re-verification note

Read-only review; the rehearsal and failure-proof commands were not re-executed
in-tree. For criteria d/f I rely on the implementer report's logs at matching HEAD
(`3ac6763`, confirmed via `git rev-parse`) plus the independent tester verdict PASS,
as scoped. Independently re-verified on disk: YAML validity and structure, absence of
all failure-masking/secret/docker/gpu/branch-filter constructs, script-name fidelity
against `frontend/package.json`, version justification against `pyproject.toml` and
local-version claims, TEST_STRATEGY §5 "if configured" premises (no markers, no
migrations, no scan config), lockfile presence, `dist/` ignored status, and zero
tracked-file leakage. At commit time, re-run the three Python gates and the five
frontend commands; after merge, observe the first live workflow run — above all the
I1 tooling question — before treating the baseline as proven green.

## Counts

- Critical: 0 | Important: 1 | Minor: 1 | FYI: 4

## Re-review

- Scope: read-only verification of the I1/M1 fix. Files read: `.github/workflows/ci.yml`
  (99 lines), `docs/task-reports/P0-007.md` (`## Fix loop` section), this review.
  Independent checks: `git status --short`, `git diff HEAD --stat`, `Select-String`
  scans of `ci.yml`, `tests/**/*.py` async scan, step-order check. No files modified
  except this append-only section.
- I1 (ruff/pytest install): RESOLVED. New step `Install lint/test tools` (`ci.yml:57-58`,
  `pip install "ruff==0.16.6" "pytest==9.1.1"`) sits after `Install package` (`:50-51`)
  and before all three gates (`:60-67`). Pins are exact (`==`) and sane (match the
  locally-verified rehearsal versions; no floating spec). No other semantics changed:
  triggers (`push` + `pull_request`, unfiltered), `permissions: contents: read`,
  concurrency group, action pins (`checkout@v4.2.2`, `setup-python@v5.3.0`,
  `setup-node@v4.1.0`), all gate commands, and CPU-only/secret-free posture intact —
  spot-scan counts all zero: `continue-on-error` 0, `|| true` 0, `secrets.` 0,
  `docker` 0, `gpu` 0, `services:` 0, `branches:` 0, `main:` 0. Sole `pytest-asyncio`
  hit is the explanatory comment (`:56`), not an install.
- M1 (timeout-minutes): RESOLVED. `timeout-minutes: 10` present on both jobs
  (`:39` python, `:71` frontend).
- pytest-asyncio omission: JUSTIFIED. Independent scan of `tests/**/*.py`:
  `async def` count 0, `asyncio|anyio|aiohttp|trio` count 0. No async test exists,
  so no plugin is needed.
- Scope hygiene: `git status --short` shows only untracked `.github/`,
  `docs/reviews/P0-007-review.md`, `docs/task-briefs/P0-007.md`,
  `docs/task-reports/P0-007.md`; `git diff HEAD --stat` empty (no tracked-file
  modification, no source/config changes). `ci.yml` is a new untracked deliverable,
  consistent with P0-007 scope.
- New findings: none.

RE-REVIEW: APPROVE — I1/M1 resolved
