# ADR-001 — Default pose model: yolo26s-pose

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The system needs a default pose model that balances accuracy and real-time
performance on the target GPU (RTX 3070) for single-household elderly monitoring.

## Decision

Use `yolo26s-pose.pt` as the default pose model, with `yolo26n-pose.pt` as fallback.
The default may only change with benchmark evidence and an ADR update.

## Consequences

- Phases 2 and 9 build against and benchmark this default first.
- Switching models later requires measured justification, not assumption.
