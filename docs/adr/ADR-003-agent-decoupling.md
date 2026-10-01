# ADR-003 — Decouple Agent/VLM from core detector

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

An Agent/VLM could enrich incidents with descriptions, but placing it in the
per-frame loop would couple core detection latency and reliability to provider uptime.

## Decision

Keep the Agent/VLM asynchronous and optional: it may enrich incidents but must never
gate, suppress, or overwrite core detector output and evidence.

## Consequences

- Phase 10 builds the agent as an async job with timeouts and a review queue.
- Core detection remains fully functional during broker/provider outages.
