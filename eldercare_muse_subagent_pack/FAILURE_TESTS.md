# Failure and Recovery Test Plan

## 1. Camera failures

### FT-001 Disconnect network/source

Expected:

- capture detects stall,
- camera becomes degraded/offline,
- no service deadlock,
- retry begins,
- event/log emitted.

### FT-002 Restore source

Expected:

- reconnect,
- camera online/reconnected event,
- frame processing resumes,
- reconnect duration measured.

## 2. Corrupt/invalid frames

Expected:

- bad frame skipped,
- counter/log incremented,
- process remains alive,
- no fabricated inference.

## 3. GPU/inference error

Inject a controlled inference exception where possible.

Expected:

- error logged,
- health reflects problem,
- no false fall event,
- recovery/restart path documented.

## 4. Database unavailable

Expected:

- persistence failure is explicit,
- system does not claim incident persisted,
- retry/degraded behavior follows design,
- no corrupt partial record.

## 5. MQTT unavailable

Expected:

- vision and database continue,
- publisher logs/buffers according to bounded policy,
- reconnects when broker returns.

## 6. VLM provider unavailable

Expected:

- enrichment becomes failed/pending according to retry policy,
- detector incident remains unchanged,
- UI can show enrichment unavailable.

## 7. Slow VLM

Expected:

- timeout enforced,
- agent worker does not exhaust unbounded workers,
- no impact on vision FPS.

## 8. Frontend unavailable

Expected:

- API/vision unaffected.

## 9. Queue overload

Force inference slower than capture.

Expected:

- stale frames dropped,
- queue remains bounded,
- latency does not grow without bound,
- dropped-frame metric increases.

## 10. Disk/storage issue

Simulate evidence write failure.

Expected:

- incident metadata identifies evidence failure,
- error is visible,
- no path traversal/fallback to unsafe arbitrary location.

## 11. Service restart

Restart API/agent worker/vision independently.

Expected:

- durable data preserved,
- health accurately reports component state,
- no duplicate database migration damage.

## 12. Long soak

Run representative stream for extended period.

Measure:

- memory trend,
- VRAM trend,
- reconnect count,
- queue depth,
- dropped frames,
- unhandled exceptions.
