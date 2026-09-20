# ADR-004 — Dataset strategy: URFD primary, UP-Fall secondary, local UAT

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

Temporal fall detection needs a practical temporal benchmark plus a robustness
check and real-world validation, without leaking final-test data into tuning.

## Decision

Use the UR Fall Detection Dataset as the primary temporal benchmark, the UP-Fall
RGB subset as secondary, and local camera recordings for UAT; tune only on the
development split and freeze configuration before final evaluation.

## Consequences

- Phase 4 tunes exclusively on the development split; Phase 11 runs frozen finals.
- Dataset binaries stay outside Git; only manifests and derived cache are tracked.
