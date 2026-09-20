# ADR-002 — Primary optimized runtime: TensorRT FP16

- **Status:** Accepted
- **Date:** 2026-09-19

## Context

The target hardware is NVIDIA (RTX 3070), so the optimization path must exploit
the platform's fastest supported inference runtime after correctness is established.

## Decision

Use TensorRT FP16 as the primary optimized runtime, following the path
PyTorch → ONNX → TensorRT FP16, with OpenVINO as an optional CPU fallback.

## Consequences

- Phase 9 benchmarks PyTorch, then ONNX, then TensorRT FP16 in that order.
- No optimization work begins before the correctness/reliability baseline exists.
