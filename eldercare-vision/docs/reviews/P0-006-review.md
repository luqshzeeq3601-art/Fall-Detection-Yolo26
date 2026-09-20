# P0-006 Review — Structured logging (fresh security/code review)

- Task: P0-006 Structured logging (`docs/task-briefs/P0-006.md`, criteria a–g)
- Spec: pack `AGENTS.md` §§9, 11, 12 + `CONSTRAINTS.md` §11
- Evidence: `docs/task-reports/P0-006.md` + independent tester verdict PASS (75 tests, live probes clean, scope-confined)
- Target (working-tree, read-only; git HEAD `cd8eef5`): `src/eldercare/common/logger.py` (new),
  `tests/unit/test_logging.py` (new), `pyproject.toml` (T201 delta), `config/logging.yaml`
- Reviewer method: read-only. No files modified, no test runs executed (to avoid
  generating `__pycache__`/`.pytest_cache` in the working tree). Findings are from
  full reads of `logger.py` (267 lines), `test_logging.py` (242 lines),
  `redaction.py` (179 lines), `logging.yaml`, the `pyproject.toml` diff,
  `git status --porcelain`, and a source grep for sinks/`print`.

## Verdict: APPROVE

No Critical or Important findings. Two Minor hardening items and three FYIs below.
All acceptance criteria a–g are plausibly met on the evidence; the Minor items are
follow-ups, not merge blockers. Recommend the coordinator re-run the three gates
(`ruff check .`, `ruff format --check .`, `pytest -v`) before commit as standard
verification-before-completion (I deliberately did not execute them in-tree).

## Findings

### Minor M1 — `logger` field emits `record.name` unsanitized while `service` is sanitized
- Location: `src/eldercare/common/logger.py:153` (`"logger": record.name`) vs
  `:154` (`"service": _sanitize_value(...)`); name construction at `:266`
  (`logging.getLogger(f"{ROOT_LOGGER_NAME}.{service}")`).
- Issue: `get_logger` interpolates the caller-supplied `service` string into the
  child logger name, but the formatter sanitizes the `service` field and leaves
  the `logger` field raw. A credential-bearing `service` string would therefore be
  masked in `service` yet appear raw in `logger`.
- Exploitability is low (service names are code constants, not external input;
  no test or probe exercises this), so this is defense-in-depth, not a live leak.
- Suggested follow-up (later task, not this one): route `record.name` through
  `sanitize_exception_message` at format time for consistency.

### Minor M2 — `json.dumps` has no fail-closed guard; NaN/Infinity extras emit non-strict JSON
- Location: `src/eldercare/common/logger.py:169`
  (`return json.dumps(data, ensure_ascii=False)` — no `try/except`, no `default=`).
- Analysis: type/circularity throws are practically unreachable — every value is
  pre-flattened by `_sanitize_value` (`logger.py:121-133`) to
  `None`/`bool`/`int`/`float`/`str`, keys are `record.__dict__` strings, and
  containers are stringified before serialization (verified, so no `default=`
  is needed and circular refs are impossible).
- Residual edge: a `float("nan")`/`inf` extra passes the `isinstance(..., float)`
  fast path untouched and serializes (via `allow_nan=True` default) as bare
  `NaN`/`Infinity` tokens — invalid strict JSON that can break downstream
  `json.loads` parsing of that line. Only reachable with an explicit hostile/odd
  caller value; the line is lost-or-corrupt, not a crash (stdlib
  `StreamHandler.emit` routes format errors to `handleError`, which does not echo
  the record message, so no secret path opens here).
- Suggested follow-up: normalize non-finite floats (e.g. to `"NaN"` string or
  `None`) in `_sanitize_value`, and/or wrap `json.dumps` with a fail-closed
  fallback line so the logging path can never throw out of `format`.

### FYI F1 — abbreviated `tok=` passes through unsanitized: in-contract, not a logger gap
- The tester-noted `tok=` pass-through is a capability boundary of the P0-005
  sanitizer, not a defect in this task's code. `redaction.py:29-31`
  (`_KEY_VALUE_SECRET_PATTERN`) only matches the full tokens
  `password|passwd|secret|token|api_?key` with `=`/`:` separators, and
  `redaction.py:21-23` (`_DEFAULT_SENSITIVE_PATTERN`, used by `redact_mapping`)
  likewise requires the full `token` substring — a bare `tok` key matches neither.
- The brief mandates reuse of P0-005 *by import* and forbids reimplementing
  redaction; the logger routes every path through it correctly. The implementer
  report discloses exactly this boundary (Assumptions: bare secrets with no
  URL-userinfo, no `key=value` shape, and no sensitive key name are outside the
  P0-005 guarantee). Judged **in-contract FYI**: if abbreviated key shapes matter,
  extend the P0-005 pattern set as a separate redaction task — do not touch it here.

### FYI F2 — propagation left at stdlib default (`True`): standard, disclosed
- `configure_logging` does not set `propagate = False` (`logger.py:221-251`), so
  records also reach handlers on the ancestor root logger *if the host ever
  attaches any*. With a bare interpreter there are none, so no double-emit
  today; the idempotency guarantee correctly covers only the single managed
  `StreamHandler(stderr)` on the `eldercare` logger. Disclosed in the report
  Assumptions. Standard library-consumer behavior; no change requested.

### FYI F3 — no payload-size cap (log-DoS via huge values)
- Very large caller strings/extras pass through unbounded; the sanitizer regexes
  scale roughly linearly, and output goes to stderr untruncated. Same exposure as
  any stdlib-logging service; the brief requires no truncation, and no cap was
  expected at foundation stage. Consider a later-phase max-field-length policy if
  high-cardinality/large-payload logging emerges. No action for P0-006.

## Verified sound (no finding)

- **Leak paths closed**: message (`_format_message`, `:171-191`, sanitizes msg
  before/after `%` rendering and each arg), mapping and positional `%s` args
  (`:177-186`, incl. non-tuple fallback), extra/bound values
  (`_format_extra`, `:193-205`: `redact_mapping` key-mask then per-value
  sanitize), exception text (`_format_error`, `:207-218`: sanitized
  `{type, message}`). Traceback object explicitly discarded (`:212`) and never
  rendered; `exc_text`/`stack_info` are in `_STANDARD_RECORD_ATTRS` (`:59-85`)
  and excluded from `extra`; tests assert `"Traceback" not in blob`.
- **Bound sensitive keys masked**: bound kwargs merge into the record and land in
  `extra` unless promoted to stable keys, so `redact_mapping` still catches
  `token`/`password`-like bound names (covered by
  `test_sensitive_bound_key_masked`).
- **Exotic values fail closed**: `_safe_str` (`:91-98`) never raises (yields
  `"***"`); non-string bound values stringified at bind time per the brief
  (`:261-263`) and sanitized again at format time.
- **`BoundLogger` sound** (`:111-118`): copies both mappings, never mutates the
  caller's `extra` or `self.extra`; call-site keys win (fixes the stdlib
  `LoggerAdapter.process` overwrite); return type remains `LoggerAdapter`.
- **Handler discipline**: marker-attr (`:53`) idempotency with in-place
  reconfigure and duplicate sweep (`:238-244`); level validated *before* any
  mutation with `ValueError` naming the bad value (`:230-234`), non-strings
  included; only sink is `StreamHandler(sys.stderr)` — grep confirms no
  `print(`/file/network handlers/`basicConfig`/traceback rendering in `src/`.
- **Hygiene**: `git status` shows only `M config/logging.yaml`, `M pyproject.toml`
  plus new `logger.py`, `test_logging.py`, brief/report docs; `redaction.py`,
  `settings.py`, `common/__init__.py`, and all forbidden paths untouched.
  `pyproject.toml` diff is a single token (`T201` appended to `select`).
  `logging.yaml` is comments-only (no parser, no `pyyaml`, stale P0-007/Phase 7
  note corrected). Tests use dummy placeholders in-process only
  (`dummyuser`/`dummy-pass-123`/`dummy-token-value-xyz`); no secrets on disk.
- **Report completeness**: on-call questions answered (3), RED→GREEN recorded
  (RED collection error → interim 21/23 with two diagnosed causes → GREEN 23/23,
  full suite 75/75), 7-row command log, assumptions/limitations/acceptance
  mapping all present. Nit (non-finding): "40 files formatted" wording describes
  a `format --check` run.

## Re-verification note

Read-only review; test/lint gates were not re-executed in-tree. Confidence rests
on (1) line-level verification of every leak/robustness/handler path above,
(2) the implementer's command log (RED→GREEN + gates PASS), and (3) the
independent tester verdict (75/75 PASS, live probes clean, scope-confined).
Re-run `ruff check .`, `ruff format --check .`, `pytest -v` at commit time;
no source changes are required by this review.

## Counts

- Critical: 0 | Important: 0 | Minor: 2 | FYI: 3
