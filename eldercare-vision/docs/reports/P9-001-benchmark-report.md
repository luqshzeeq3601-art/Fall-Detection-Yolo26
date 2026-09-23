# P9-001 Benchmark Report — BASELINE (no optimization performed)

> **READ FIRST:** This is a BASELINE report. No optimization, conversion,
> tuning, or training was performed. Numbers below were measured on a
> **CPU-only Windows CI machine with a deterministic FAKE predictor** and
> describe **harness overhead + CPU pipeline stages only — NOT model
> performance and NOT RTX 3070 results.** Nothing here claims an optimized,
> accelerated, or production-target state.

## Environment (measured, from artifact)
- Host: win32, Python 3.10.8, numpy 2.2.6, opencv 5.0.0.93
- torch: NOT INSTALLED · ultralytics: NOT INSTALLED · CUDA: unavailable
- Device: cpu · VRAM: N/A · RSS: N/A (platform lacks `resource`)
- Commit: `d56d9a3e891ee9592afd7112b20d91f79b3db8da`
- Runtime config: yolo26s-pose.pt / PyTorch FP32 / device 0 / imgsz 640 /
  batch 1 / bytetrack / fall config v1.0.0 (recorded, not executed — no weights on CI)

## Methodology
- Harness: `benchmarks/scripts/benchmark_inference.py` → `eldercare.benchmark.harness`
- Input: deterministic synthetic uint8 640×480, seed 42, 340 frames/run
  (identical ordering across reps, byte-verified by tests)
- Warm-up: 40 frames/run, excluded from all statistics (call-count proven)
- Measured: 300 frames × 3 repetitions, CUDA sync bracketing where available
- Stages: preprocess → predict+adapt (sync-bracketed) → track-history → FSM

## Measurements (fake predictor → harness overhead, NOT model latency)
- FPS (median of runs): **475.01** (runs: 422.69 / 475.01 / 534.10)
- Mean: 1.880 ms · Median: 1.757 ms · P90: 2.420 ms · P95: 2.715 ms · P99: 3.567 ms
- Per-stage means: preprocess 0.019 · predict(fake) 0.019 · adapt 0.130 ·
  track 0.049 · fsm 0.083 ms
- Variability: CV of run means **0.108** (shared-machine jitter across reps;
  no run discarded — all three retained in the artifact)

## GPU memory
- Baseline/peak VRAM: N/A (no CUDA device). Must be re-measured on the RTX 3070 host.

## Limitations
- Fake predictor: numbers carry ZERO information about YOLO inference cost.
- CPU-only host: no CUDA sync exercised (fallback path proven by stub test).
- 640×480 synthetic frames, not the fixed benchmark clip (no committed clip exists; datasets untouched per constraints).
- CI-scale run, not a longevity benchmark.

## Reproduction
- This run: `python benchmarks/scripts/benchmark_inference.py --predictor fake --warmup 40 --frames 300 --reps 3 --out benchmarks/results/p9_001_baseline.json`
- Target host (RTX 3070, torch+ultralytics+CUDA installed):
  `python benchmarks/scripts/benchmark_inference.py --predictor ultralytics --warmup 40 --frames 300 --reps 3 --out benchmarks/results/p9_001_rtx3070_pytorch.json`
- Artifact: `benchmarks/results/p9_001_baseline.json` (schema 1.0, units explicit).

## Forbidden claims (none made)
- Not optimized, not accelerated, production target NOT achieved.
- No README/resume numbers taken from this run.
- Model training: NOT STARTED.
