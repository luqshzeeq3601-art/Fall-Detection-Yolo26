# P0-005 Review — `.env.example`, secret loading/redaction (fresh security review)

**Reviewer stance:** fresh reviewer; implementation conversation NOT seen. Reviewed working tree on disk only, read-only (no target files modified, no fixes implemented). Live probes executed read-only via `python -c` / temp scripts outside the repo (no repo writes).
**Target:** `src/eldercare/common/settings.py` (112 lines) + `src/eldercare/common/redaction.py` (127 lines), `.env.example` (25 lines), `pyproject.toml` deps delta, `tests/unit/test_settings.py` (174 lines) + `tests/unit/test_redaction.py` (144 lines).
**Brief:** `docs/task-briefs/P0-005.md` (criteria a–g, forbidden scope). **Spec:** pack `AGENTS.md` §§9, 11, 12 + `CONSTRAINTS.md` §9.
**Evidence:** implementer report `docs/task-reports/P0-005.md` + claimed independent tester verdict PASS (46 tests, all a–g, reconciliation byte-match, no `.env`, clean scan).
**Git:** HEAD `20dbd28` (matches brief dependency); working tree: `M .env.example`, `M pyproject.toml`, untracked `src/eldercare/common/{settings,redaction}.py`, `tests/unit/test_{settings,redaction}.py`, `docs/task-reports/P0-005.md`, `docs/task-briefs/P0-005.md` (coordinator input). No commit by reviewer.

## Verdict: REQUEST CHANGES

Two Important findings below are defects in the security control itself, both reproduced live against the on-disk code: (1) `sanitize_exception_message` leaves a credential fragment in log text when the password contains `/` (also `?`, `#`, space) — a direct break of AC-P0-005f's "never leak" path for a realistic password class; (2) `redact_mapping` default path throws `TypeError` on non-string dict keys — a crash inside a sanitization helper. Both are small, localized fixes. All other criteria corroborate. Downgrade to APPROVE after fixes + re-verification note (§Re-verification).

## Findings

### Critical — none (0)

No hardcoded secret, no committed `.env`, no secret-echoing error path in the common case, no forbidden-file changes (see corroboration).

### Important (2)

- **[Important] `sanitize_exception_message` leaks a credential fragment when the URL password contains `/` (also `?`, `#`, whitespace).**
  `src/eldercare/common/redaction.py:24-26` — `_URL_WITH_USERINFO_PATTERN` defines userinfo as `[^/\s@?#]+`, so any password containing those characters terminates the match early and the remainder survives into "sanitized" output.
  Reproduced live (read-only): `sanitize_exception_message('err url=rtsp://user:p@ss/word@h:554/s end')` → `'err url=rtsp://***@ss/word@h:554/s end'` — the fragment `ss/word@h` (most of the password plus a second `@`) remains in the log line. The sibling `urlsplit`-based `_strip_userinfo` (`:32-55`) handles the same input correctly, so only the regex path is broken. This defeats AC-P0-005f for exactly the password class the implementer's own Limitations section flags as plausible (special-character passwords), and the existing tests never exercise it (all dummy passwords are `[a-z0-9-]`-only).
  Fix (suggestion, not implemented): replace the regex substitution with a `urlsplit`-based rewrite of each URL-looking token, or widen the userinfo matcher to span up to the *last* `@` before the authority terminator (`[^/\s]*@` greedy to last `@`). Add tests with passwords containing `/`, `?`, `#`, `@`, space, and percent-encoding.
- **[Important] `redact_mapping` default path raises `TypeError` on non-string dict keys — crash inside a security-sanitization helper.**
  `src/eldercare/common/redaction.py:99-100` — `_DEFAULT_SENSITIVE_PATTERN.search(key)` assumes `key` is a string. Reproduced live: `redact_mapping({1: 'x', 'password': 'y'})` → `TypeError: expected string or bytes-like object`. The caller-supplied-set branch (`:105-107`) already coerces via `str(key).lower()` and is safe — only the default branch is broken. A throw in the sanitizer risks callers falling back to logging the original mapping (fail-open logging path) and is a minor availability break in observability code.
  Fix (suggestion): coerce with `str(key)` in the default branch exactly as the explicit-set branch does. Add a test with int/None keys asserting no-throw and correct redaction of string keys.

### Minor (4)

- **[Minor] `_strip_userinfo` drops IPv6 brackets (and lowercases host): lossy redaction, malformed output.**
  `src/eldercare/common/redaction.py:44-51` rebuilds netloc from `parts.hostname` (`::1`) + port without re-adding `[]`. Reproduced: `redact_rtsp_url('rtsp://u:p@[::1]:554/s')` → `'rtsp://::1:554/s'` (invalid URL; brackets gone, host lowercased). No credential leaks — direction is fail-closed — but host context for debugging is corrupted. Already disclosed in the report ("strips IPv6 brackets"); still worth fixing by re-bracketing when `':' in host` (and noting the lowercase normalization). Non-blocking for boundary-only phase; add an IPv6 round-trip test.
- **[Minor] Whitespace-only required values accepted (`min_length=1` counts spaces).**
  `src/eldercare/common/settings.py:36-38`. Reproduced: `POSTGRES_USER='   '` loads successfully. Fail-closed is weakened against blank/space config (a `POSTGRES_PASSWORD=' '` would also pass). Recommend `strip()`-aware validation (`min_length` + `strip_whitespace=True` or an explicit non-blank validator) for the three requireds. Small test addition.
- **[Minor] Composed `DATABASE_URL` interpolates user/password raw (no URL-encoding).**
  `src/eldercare/common/settings.py:85-88`. Passwords containing `@`/`:`/`/` compose into an ambiguous URL (availability failure / credential mis-parse downstream). Correctly disclosed in the report Limitations and consistent with `docker-compose.yml:64,83` template behavior, so not a new violation — but the follow-up should apply `urllib.parse.quote_plus` to user/password at composition time (and document that direct `DATABASE_URL` wins and is used verbatim). Note `redacted_summary()` strips userinfo regardless, so no leak amplification was observed.
- **[Minor] `RTSP_URL` validator accepts any `scheme://host`, not restricted to `rtsp(s)://`.**
  `src/eldercare/common/settings.py:59-74`. Disclosed assumption in the report ("generic URL check"). Satisfies the brief as written, but when a later phase dials this URL it becomes the SSRF allowlist — recommend pinning the scheme allowlist (`rtsp`, `rtsps`, and only if needed `rtspu`) at the consumption point, not necessarily here. Add a comment or follow-up pointer.

### FYI (6)

- **[FYI] `hide_input_in_errors=True` verified live, not just claimed.**
  `src/eldercare/common/settings.py:30-34` sets it, and probes confirm: (a) failing `MQTT_PORT='notaport'` with `POSTGRES_PASSWORD='supersecret-pw-123'` set → error text contains no secret; (b) credentialed `RTSP_URL='rtsp://admin:rtsp-secret-xyz@cam:badport/s'` failing port validation → error text contains no secret, only the generic validator message. Custom validators (`:46-74`) never interpolate values. Good.
- **[FYI] `extra="ignore"` is brief-mandated and acceptable here.**
  `settings.py:32`. Process env always carries unrelated vars, so `ignore` is the operable choice; a misspelled *required* still fail-closes via missing-field `ValidationError`. Residual: misspelled *optionals* (e.g. `MQTT_PROT`) are silently dropped — consider documenting this in the module docstring for operators. No action required.
- **[FYI] `env_file=".env"` auto-load implications are documented and contained.**
  `settings.py:31` + module docstring (`:1-5`) + `.env.example:1-2` header ("never commit"). Missing file is silently ignored (disclosed). `.gitignore` covers `.env` and `.env.*` (verified on disk); `Test-Path .env` → False. Precedence (init > env > dotenv, standard pydantic-settings) could be one docstring line in a follow-up; not blocking.
- **[FYI] `redact_token` partial reveal (first2+last2 for len ≥ 8) is spec-mandated.**
  `redaction.py:78-86`, brief-mandated, tested (`test_redaction.py:66-75`). Verified live: non-string/int/bytes/None/empty/short all → `"***"` without throwing. The 4-char reveal is inherent to the brief's format; acceptable, recorded for awareness.
- **[FYI] `redact_mapping` with an explicitly empty key set redacts nothing.**
  `redaction.py:105-110` — caller-supplied set *replaces* the default (tested at `test_redaction.py:103-109`). `settings.py:109` passes a concrete 2-key set, so the in-repo call is safe; just a footgun for future callers — a docstring caution suffices.
- **[FYI] Sanitizer pattern notes (safe direction / disclosed limits).**
  Live probes: `postgresql://adm:s3cret@pg:5432/d` fully stripped; `password=…`/`apikey:…` masked (`_KEY_VALUE_SECRET_PATTERN`, `:27-29`) including over-masking of trailing punctuation (safe direction); `auth`-as-key is not in the key=value pattern (URL path covers `auth` via userinfo only); standalone tokens with no key context are undiscoverable — all consistent with the report's disclosed limitation. Recommend extending the key=value alternation with `auth` when the Important regex fix is made.

## Criterion-by-criterion corroboration (a–g)

- **(a) `.env.example` documents every Settings field; `POSTGRES_*` byte-match; zero real secrets — CORROBORATED.**
  9 keys in `.env.example:8-25` vs 9 `Settings.model_fields` (`settings.py:36-44`); reconciliation test (`test_settings.py:154-173`) parses compose `${POSTGRES_*}` refs, example keys, and model fields in-test with no hardcoded list. `POSTGRES_USER/PASSWORD/DB` placeholders are `CHANGEME`; `DATABASE_URL/RTSP_URL/VLM_API_KEY` empty; `MQTT_HOST=mosquitto`, `MQTT_PORT=1883`, `LOG_LEVEL=INFO`; every key has a one-line purpose/required/default comment; precedence documented in file (`:4-5`), module docstring (`settings.py:7-11`), and report. Grep-equivalent scan by reading: only `<password>`/`<user>` placeholder tokens in comments; no credentialed URLs.
- **(b) Missing required → `ValidationError` naming the field (all three) — CORROBORATED.**
  Requireds have no defaults (`settings.py:36-38`); parametrized test (`test_settings.py:45-54`) asserts each missing name appears in the error. `hide_input_in_errors` additionally verified live (see FYI).
- **(c) Malformed port/URL → `ValidationError` — CORROBORATED.**
  `MQTT_PORT` int + `ge=1, le=65535` (`:41`); parametrized bad-port test incl. `0/99999/-1/alpha/float` (`test_settings.py:57-64`); `RTSP_URL`/`DATABASE_URL` validators reject missing scheme/host and non-numeric ports with generic messages (`settings.py:46-74`; tests `:67-69,106-108`). `LOG_LEVEL` Literal both directions (`:120-128`).
- **(d) `DATABASE_URL` precedence both directions — CORROBORATED.**
  Property (`settings.py:76-88`): non-empty direct wins, else composed `postgresql://<user>:<password>@postgres:5432/<db>` mirroring compose `:64,83`; empty-string falls back to composed (`test_settings.py:84-103`, three tests). Single documented precedence in docstring + example + report.
- **(e) Redaction incl. edge cases; raw never returned on failure — CORROBORATED with the two Important exceptions.**
  Userinfo stripping preserves host/port/path/db and query (`redaction.py:32-55`); sentinel on unparseable incl. non-string (`:34-35,40-46`); empty passthrough (`:36-37`); token short/empty/None/non-string → `"***"` (verified live); mapping case-insensitive default + exact caller set + non-mutation (tests `:78-115`); `redacted_summary` masks password/key and strips both URLs (live leak-check False). Exceptions to "never leaks": Important finding 1 (special-char password fragment via regex path) and robustness gap Important finding 2.
- **(f) Exception/log sanitized — CORROBORATED for tested shapes; gap beyond them.**
  Tests cover `str(exc)` with credentialed RTSP URL and a formatted log line with RTSP+PG URLs and `key=value` secrets (`test_redaction.py:118-144`). Live probes confirm host context preserved (`camera01.local`) and `retry=3` intact. Gap: passwords containing `/ ? #` whitespace (Important 1) are outside the tested shapes.
- **(g) Gates PASS; ≥10 new tests — CORROBORATED on structure (not re-executed by reviewer per read-only scope; report + tester evidence).**
  Report command log: `pip install -e .` PASS, `ruff check` PASS after source-only fixes, `ruff format --check` PASS (35 files), `pytest` 46 passed (45 new + P0-002 smoke). Test files on disk contain 45 new tests by count (well over the ≥10 minimum) covering all 10 brief-required items. Type hints on all public functions; no bare `except` (only `except (ValueError, AttributeError, TypeError)` / `except ValueError`); no third-party imports in `redaction.py` (stdlib only: `re`, `collections.abc`, `typing`, `urllib.parse`).

## Scope check — CLEAN

- Tracked diff vs HEAD: only `.env.example` (full-key rewrite) + `pyproject.toml` (`dependencies` block only: `pydantic>=2`, `pydantic-settings>=2`; no other sections touched) — matches "files allowed".
- New files: `settings.py`, `redaction.py`, `tests/unit/test_settings.py`, `tests/unit/test_redaction.py`, `docs/task-reports/P0-005.md` — all allowed. `common/__init__.py` untouched (docstring-only, verified). `docker-compose.yml` byte-identical to HEAD scope (read-only reference; `git status` shows no modification). No `frontend/`, `deployment/`, CI, `config/*.yaml`, `README.md`, LICENSE, or `src/eldercare/{vision,fall_engine,api,db,mqtt,agents,incidents}/` changes. No DB/MQTT/API/camera/logging integration code. Deps delta minimal and sanely pinned (`>=2` lower bounds ≤ installed 2.13.4/2.15.0 per report's `pip show` record). No `.env` on disk; `.gitignore` covers `.env`/`.env.*`.

## Re-verification note

After fixes: (1) re-run the two live probes — `sanitize_exception_message` over passwords containing `/ ? # @` space and `%40`, asserting zero residual fragments, and `redact_mapping` over int/None keys asserting no-throw; (2) add the corresponding regression tests (special-char passwords, non-string keys, IPv6, whitespace-only requireds); (3) full gates `pip install -e .`, `ruff check .`, `ruff format --check .`, `pytest -v` (expect 46+ passed incl. new tests); (4) confirm `git status` shows no forbidden-file changes. Reviewer did not run the suite (read-only review scope; environment parity left to the implementer's recorded log and the tester's independent PASS).

## Re-review (2026-09-19, fresh re-reviewer, read-only + live probes, no files modified except this appendix)

**RE-REVIEW: APPROVE — both Important findings resolved.**

1. **Important 1 (sanitize regex leak) — RESOLVED.** Live probes against fixed code (dummy values only): `p@ss/w`, `a?b`, `a#b`, `a b` in `rtsp://user:<pw>@camera01.local:554/stream1` all → `'err url=rtsp://***@camera01.local:554/stream1 end'` — raw password absent, host preserved. Original failure mode (`p@ss/w` fragment leak) no longer reproduces.
2. **Important 2 (redact_mapping TypeError) — RESOLVED.** `redact_mapping({1:'x','password':'y',None:'z',('t','k'):'v'})` → `{1:'x','password':'***',None:'z',('t','k'):'v'}` — no throw, string keys still masked, non-string keys pass through untouched. Fix is the `isinstance(key,str)` guard at `redaction.py:152`, matching the suggested fix.
3. **Regression tests — 6 new, all pass.** `test_sanitize_exception_message_adversarial_passwords_no_leak` (5 params: slash/question/hash/space/all-specials) + `test_redact_mapping_non_string_keys_no_throw` (int/None/tuple keys) at `tests/unit/test_redaction.py:147-175`. `pytest tests/unit/test_redaction.py -v` → **27 passed**.
4. **No new leak/throw (extra probes):** multi-`@` password (`p@ss@word`) → `rtsp://***@cam:554/s` (full mask); percent-encoded (`p%40ss%2Fw`) → full mask; IPv6 with creds → `rtsp://***@[::1]:554/s` (brackets preserved on this path); userinfo-free URL unchanged (no over-masking); two URLs in one line each masked independently (no window-merge). No under-masking observed. (Pre-existing Minor on `_strip_userinfo` IPv6 bracket handling is unchanged and out of scope for this re-review.)
5. **Scope — CLEAN.** `git status --short`: only `M .env.example`, `M pyproject.toml` (tracked) + untracked `redaction.py`, `settings.py`, `test_redaction.py`, `test_settings.py`, review/brief/report docs — identical file set to the first review; `git diff HEAD --stat` shows only the two allowed tracked files. No new findings; no severity raised.
