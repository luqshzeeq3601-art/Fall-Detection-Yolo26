# Code Review Report: P5-005 — Incident List, Detail & Evidence Streaming APIs

- **Task ID:** P5-005
- **Reviewer:** Independent Reviewer (Superpowers `requesting-code-review`)
- **Date:** 2026-09-23
- **Verdict:** APPROVE (0 Critical, 0 Important)

## 1. Scope & Verification

The review examined the implementation of incident list/detail querying and evidence streaming endpoints against `API_SPEC.md` and repository architectural standards:
- `src/eldercare/api/routers/incidents.py`
- `src/eldercare/api/app.py`
- `src/eldercare/api/schemas.py`
- `src/eldercare/api/__init__.py`
- `tests/unit/test_api_incidents.py`

## 2. Review Findings & Audit

### A. Contract Conformance & Error Consistency
- `GET /incidents` accurately exposes filtering on camera, detector state, human review decisions, and ISO timestamp bounds with limit/offset pagination.
- `GET /incidents/{incident_id}` reliably returns nested `evidence`, `reviews`, and `enrichments` relations.
- Missing resources return 404 with exact envelope `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.

### B. Security & Filesystem Sandboxing
- `GET /incidents/{incident_id}/evidence/{evidence_id}` verifies ownership via the database record first, then passes the storage path to `EvidenceStorage.resolve_safe_path()`.
- Path traversal sequences (`../`, root `/`, absolute drives) are caught and rejected prior to filesystem I/O with HTTP 400 `PATH_TRAVERSAL_FORBIDDEN`.
- `X-Evidence-SHA256` header is computed/returned on streaming responses.

### C. Detector Immutability
- Read endpoints expose detector outputs (`fall_score`, `model_name`, `evidence_features`) verbatim without allowing in-flight mutations.

## 3. Findings Summary

- **Critical:** 0
- **Important:** 0
- **Minor / Observational:** None.

## 4. Final Verdict

**APPROVE**. Ready for atomic commit and progression to P5-006.
