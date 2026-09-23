# P10-003 — Review: Provider Client Timeout, Retry, and Error Normalization

## Review Checklist
- [x] **Domain Error Taxonomy**: `ProviderClientError`, `ProviderTimeoutError`, `ProviderRateLimitError`, `ProviderAuthError`, `ProviderMalformedResponseError`, `ProviderConnectionError` implemented.
- [x] **Retry Gating**: Retries transient faults (429, 500, 502, 503, 504, timeout, connection drop); fails fast on 400, 401, 403, 422.
- [x] **Credential Protection**: Zero credential leakage in reprs, log statements, or exception strings.
- [x] **Hermetic Testing**: `MockVLMProvider` and injectable `sleep_func` allow zero-delay unit tests without external network dependencies.
- [x] **Pipeline Isolation**: Client is asynchronous and fully decoupled from the deterministic fall detection loop.
- [x] **Code Quality**: Passes `ruff check`, `ruff format --check`, and 100% of unit tests.

## Verdict
**APPROVE** — P10-003 meets all architectural, security, and reliability requirements.
