# P0-002 Review — Configure Python project, Ruff, pytest (fresh review)

- Verdict: **APPROVE**
- Reviewer: fresh reviewer (no prior implementation context; disk-only, read-only except this file)
- Date (UTC): 2026-09-19
- Target: `eldercare-vision/` at git HEAD `8303c16` + uncommitted working tree (implementer made no commit, per brief)
- Sources: brief `docs/task-briefs/P0-002.md` (criteria a–f + forbidden scope), spec `eldercare_muse_subagent_pack/AGENTS.md` §§9/11/12 only, evidence `docs/task-reports/P0-002.md` + tester verdict PASS 6/6 (as cited in task)

## Working tree reviewed

`git status --short` (uncommitted vs HEAD `8303c16`):

```text
M .gitignore
M pyproject.toml
?? docs/task-briefs/P0-002.md
?? docs/task-reports/P0-002.md
?? src/eldercare/__init__.py
?? src/eldercare/agents/__init__.py
?? src/eldercare/api/__init__.py
?? src/eldercare/common/__init__.py
?? src/eldercare/db/__init__.py
?? src/eldercare/fall_engine/__init__.py
?? src/eldercare/incidents/__init__.py
?? src/eldercare/mqtt/__init__.py
?? src/eldercare/vision/__init__.py
?? tests/conftest.py
?? tests/unit/test_package_import.py
```

`git diff HEAD --stat` (tracked files): 2 files changed (`pyproject.toml`, `.gitignore`), 30 insertions, 4 deletions. No changes under `frontend/`, `deployment/`, `config/`, `docker-compose.yml`, `README.md`, CI paths.

## Findings

### [Minor] License field is an unconfirmed MIT placeholder; no LICENSE file — follow-up, does NOT block P0-002

- Location: `eldercare-vision/pyproject.toml:6` (`license = { text = "MIT" }`); repo root has no `LICENSE` file (verified: `git ls-files | Select-String LICENSE` empty, `Test-Path LICENSE` false).
- The brief requires license metadata in `[project]` — satisfied. It does not require a `LICENSE` file, and adding one would fall outside this task's allowed-files list.
- The implementer explicitly flagged this as an unresolved decision for the coordinator (report §Unresolved decisions) rather than silently asserting it — correct handling.
- Disposition: non-blocking. Recommend a later task confirm the license choice and, if MIT is accepted, add a `LICENSE` file. Do not fold it into P0-002.

### [FYI] `asyncio_mode = "auto"` relies on environment-provided pytest-asyncio, not a declared dependency — compliant as read, note for later phases

- Location: `eldercare-vision/pyproject.toml:28-31`.
- Brief wording ("only if pytest-asyncio is declared") is satisfied under the installed-baseline reading: the brief itself lists pytest-asyncio 1.4.0 as installed, and the report cites `pytest --help` (`asyncio_mode` ini option exists) plus the live suite header (`asyncio: mode=auto`). Re-verified here: `pytest -v` header shows `asyncio: mode=auto` with plugin `asyncio-1.4.0` loaded.
- Note (not a defect): since `pyproject.toml` intentionally declares no dependencies (per forbidden scope, so `pip install -e .` stays network-free), a fresh environment without pytest-asyncio would not get `auto` semantics. Dependency pinning is explicitly a later phase, so no action now.

### [FYI] Ruff format file count 22 (report) vs 23 (re-verification) — explained, still clean

- Report: `ruff format --check .` → `22 files already formatted`. Re-verification: `23 files already formatted`. The delta is the untracked coordinator-owned brief `docs/task-briefs/P0-002.md`-adjacent working-tree content added after the implementer run, not source churn. `ruff check .` → `All checks passed!` in both. No action.

### [FYI] Untracked `docs/task-briefs/P0-002.md` is coordinator-owned, not an implementer scope violation

- It appears in `git status` as `??` alongside the implementer's files. File-ownership rules in the brief assign briefs to the coordinator; the implementer's report correctly lists only allowed paths. No action.

### [FYI] LF→CRLF git advisory warnings are pre-existing repo behavior

- Seen on `git diff` for both touched files; the report already discloses this as pre-existing, and new-file line endings match repo convention. No action.

## Checklist

### 1. Config correctness — PASS

- `pyproject.toml` vs brief §Requirements:
  - `[project]`: `name = "eldercare-vision"` ✓, `version = "0.1.0"` ✓, `requires-python = ">=3.10"` ✓, `description` one-line POC summary ✓, `license = { text = "MIT" }` ✓ (placeholder, see Minor above).
  - `[build-system]`: `requires = ["setuptools>=61"]`, `build-backend = "setuptools.build_meta"` ✓.
  - `[tool.setuptools.packages.find] where = ["src"]` ✓ — src-layout resolves: `importlib.metadata.version('eldercare-vision')` → `0.1.0`, `python -c "import eldercare; print(eldercare.__version__)"` → `0.1.0` in this review session (editable install present; `*.egg-info/` correctly gitignored).
  - `[tool.ruff]`: `target-version = "py310"` ✓, `line-length = 100` ✓.
  - `[tool.ruff.lint] select = ["E","F","I","N","W","B","UP"]` ✓ — meets the "at minimum" set; report correctly notes Ruff's built-in `B` rules keep the install dependency-free.
  - `[tool.ruff.lint.isort] known-first-party = ["eldercare"]` ✓.
  - `[tool.ruff.format] quote-style = "double"` ✓ (also Ruff default; harmless pin).
  - `[tool.pytest.ini_options]`: `testpaths = ["tests"]` ✓, `pythonpath = ["src"]` ✓, `asyncio_mode = "auto"` ✓ with installed pytest-asyncio 1.4.0 (see FYI). No `dependencies` key — correct per forbidden scope.
- `src/eldercare/__init__.py`: docstring + `__version__ = "0.1.0"` only ✓. All 8 direct subpackage `__init__.py` files (`agents, api, common, db, fall_engine, incidents, mqtt, vision`) present, docstring-only ✓ (spot-checked `vision`, `common`; grep over `src/` finds no `def `/`class `/third-party imports/`threshold` logic).
- `tests/conftest.py`: docstring-only, no fixtures, no `sys.path` hack — "path-safe" via `pythonpath = ["src"]` ✓.
- `tests/unit/test_package_import.py`: asserts importable `eldercare` and non-empty string `__version__` ✓. No `tests/unit/__init__.py` (`Test-Path` false) — correct default per brief since collection works (`configfile: pyproject.toml`, `testpaths: tests`).

### 2. Forbidden scope — PASS (no violations)

- No app logic: grep over `src/**/*.py` for runtime imports / `def`/`class`/`except:`/thresholds returns nothing.
- No runtime deps: no `[project] dependencies` in `pyproject.toml`.
- No `frontend/`, Docker, CI, `config/*.yaml`, logging-implementation, or README changes: `git diff HEAD --stat` for those paths is empty; `git status` shows none touched.
- No `git init`/`git commit` by implementer: HEAD still `8303c16`, changes uncommitted ✓.
- No invented benchmarks/thresholds: none in code or report.
- Files changed map exactly to the allowed list (report file + coordinator brief aside).

### 3. Security/hygiene — PASS

- No secrets in any new/changed file (contents inspected: docstrings, version string, smoke test, TOML, gitignore). `.env.example` untouched (placeholder `CHANGEME` values only, pre-existing from P0-001).
- `.gitignore` is additive-only: full `git diff HEAD -- .gitignore` shows only additions (`.env.*`, `*.log`, `.coverage`, `coverage.xml`, `htmlcov/`); all P0-001 entries kept, including pre-existing `.env`, `*.pem`, `*.key`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/` ✓. AC-P0-002f coverage requirement (`.env*`, logs, coverage) met.
- AGENTS.md §11 (never commit `.env`/keys/credentials/datasets/recordings): nothing of that kind staged or added ✓.
- AGENTS.md §9: Ruff+pytest baselines enforced; type-hint/Pydantic/logging mandates have no applicable surface in this logic-free task — no violation.
- AGENTS.md §12: no commits made by implementer, no formatting churn (`ruff format --check` clean), user/coordinator files preserved.

### 4. Report completeness — PASS

- RED→GREEN evidence present with exact failure/passing snippets (`ModuleNotFoundError: No module named 'eldercare'` → `1 passed`) ✓.
- Version citations present and match this reviewer's environment: Python 3.10.11, ruff 0.16.6, pytest 9.1.1, pytest-asyncio 1.4.0, `pytest --help` ini-option confirmation, `ruff --version` ✓. The `pip show` cp1252 logging workaround is disclosed, not hidden.
- Command log: 10 numbered commands with PASS/FAIL outcomes, including the expected RED FAIL and the `--no-deps` justification for the offline editable install ✓.
- Assumptions/limitations/unresolved-decisions sections present; license placeholder and `tests/unit/__init__.py` omission explicitly recorded ✓.
- All six acceptance criteria mapped to PASS with the commands that prove each ✓.

## Re-verification note (independent, read-only; no source files modified)

Re-ran from `eldercare-vision/` on the same working tree:

| Check | Result |
|---|---|
| `python -c "import eldercare; print(eldercare.__version__)"` | `0.1.0` ✓ (AC-e) |
| `python -c "import importlib.metadata; ...version('eldercare-vision')"` | `0.1.0` ✓ (AC-a: editable install resolves) |
| `ruff check .` | `All checks passed!` ✓ (AC-b) |
| `ruff format --check .` | `23 files already formatted` ✓ (AC-c; count delta explained above) |
| `pytest -v` | `1 passed in 0.02s`, header `asyncio: mode=auto` ✓ (AC-d) |
| `python --version` / `ruff --version` / `pytest --version` | `Python 3.10.11` / `ruff 0.16.6` / `pytest 9.1.1` — match report ✓ |
| `git status --short` / `git diff HEAD --stat` | only allowed paths; 2 tracked files changed ✓ (AC-f scope half) |
| Secret/hygiene scan of new-file contents | no secrets; `.gitignore` covers `.env*`, logs, coverage ✓ (AC-f) |

No files were edited during review; the only write is this review document itself.

## Verdict rationale

All six acceptance criteria are independently confirmed on disk, config values match the brief exactly, forbidden scope is clean, hygiene passes, and the report is complete with honest RED→GREEN and version evidence. The single Minor (unconfirmed MIT placeholder, no LICENSE file) is explicitly surfaced by the implementer and is a coordinator follow-up by design — it does not fail any P0-002 criterion. No Critical or Important findings. **APPROVE** with no required changes.
