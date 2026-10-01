# P9-002 Benchmark Report — PyTorch CUDA Baseline on NVIDIA RTX 3070

## Summary
Official baseline benchmark of `yolo26s-pose.pt` using real PyTorch CUDA inference on the target NVIDIA GeForce RTX 3070 8GB GPU.

## Environment (Measured)
- Host: Windows 10 (10.0.26200), Python 3.10.11
- GPU: NVIDIA GeForce RTX 3070 (8192 MB VRAM), Driver 616.92
- CUDA: 12.1 (Compute Capability 8.6)
- cuDNN: 90100 (9.1.0)
- PyTorch: 2.5.1+cu121
- Ultralytics: 8.4.142
- NumPy: 2.2.6
- OpenCV: 5.0.0.93

## Benchmark Methodology
- Model: `yolo26s-pose.pt` (FP32)
- Input: Deterministic synthetic NumPy frames (640x480 uint8 RGB, seed 42)
- Warmup: 40 frames per repetition (excluded from timing)
- Repetitions: 3 runs of 300 measured frames (900 total measured frames)
- Synchronization: `torch.cuda.synchronize()` bracketing inference and end-to-end stages

## Measured Results

| Metric | Measured Value |
|---|---|
| Median Throughput (FPS) | **64.54 FPS** (Run 1: 43.06, Run 2: 66.15, Run 3: 64.54) |
| Mean Total Latency | **13.436 ms** |
| Median Total Latency (p50) | **13.209 ms** |
| p90 Latency | **13.956 ms** |
| p95 Latency | **14.352 ms** |
| p99 Latency | **16.649 ms** |
| Min / Max Latency | 12.943 ms / 21.596 ms |
| Synchronized Inference (Mean) | **13.365 ms** |
| Preprocess Stage (Mean) | **0.007 ms** |
| Model Predict Stage (Mean) | **13.316 ms** |
| Pose Adapt Stage (Mean) | **0.050 ms** |
| Tracking Stage (Mean) | **0.002 ms** |
| FSM Stage (Mean) | **0.0001 ms** |
| Peak VRAM Usage | **104.01 MB** |
| Baseline / Peak RSS Memory | **769.21 MB / 1535.34 MB** |
| Variability (CV of Run Means) | **0.0124 (1.24%)** |

## Artifact
- Raw JSON artifact: `benchmarks/results/p9_002_pytorch_baseline.json`
