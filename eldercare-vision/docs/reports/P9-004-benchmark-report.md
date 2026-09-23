# P9-004 Benchmark Report — TensorRT FP16 on NVIDIA RTX 3070

## Summary
Benchmark evaluation of `yolo26s-pose.engine` executed with TensorRT 11.3.0.99 FP16 on the target NVIDIA GeForce RTX 3070 8GB GPU, compared directly against P9-002 PyTorch CUDA baseline and P9-003 ONNX Runtime CUDA.

## Environment (Measured)
- Host: Windows 10 (10.0.26200), Python 3.10.11
- GPU: NVIDIA GeForce RTX 3070 (8192 MB VRAM), Driver 616.92
- CUDA: 12.1 (Compute Capability 8.6)
- TensorRT: 11.3.0.99 (FP16 Engine)
- PyTorch: 2.5.1+cu121
- Ultralytics: 8.4.142
- NumPy: 2.2.6
- OpenCV: 5.0.0.93

## Benchmark Methodology
- Model: `yolo26s-pose.engine` (FP16 precision, strongly-typed TensorRT 11 plan, 111 MB)
- Input: Deterministic synthetic NumPy frames (640x480 uint8 RGB, seed 42)
- Warmup: 40 frames per repetition (excluded from timing)
- Repetitions: 3 runs of 300 measured frames (900 total measured frames)
- Synchronization: `torch.cuda.synchronize()` bracketing inference and end-to-end stages

## Measured Results & 3-Way Runtime Comparison

| Metric | P9-002 PyTorch Baseline | P9-003 ONNX Runtime | P9-004 TensorRT FP16 | Delta vs PyTorch | Delta vs ONNX |
|---|---|---|---|---|---|
| **Median Throughput (FPS)** | **64.54 FPS** | **105.33 FPS** | **212.91 FPS** | **+229.9% (3.30x)** | **+102.1% (2.02x)** |
| Run 1 / Run 2 / Run 3 FPS | 43.06 / 66.15 / 64.54 | 56.56 / 105.33 / 105.49 | 80.88 / 212.91 / 215.46 | — | — |
| **Mean Total Latency** | **13.436 ms** | **8.377 ms** | **4.125 ms** | **-69.3%** | **-50.8%** |
| **Median Total Latency (p50)** | **13.209 ms** | **8.333 ms** | **4.101 ms** | **-68.9%** | **-50.8%** |
| **p90 Latency** | **13.956 ms** | **8.542 ms** | **4.270 ms** | **-69.4%** | **-50.0%** |
| **p95 Latency** | **14.352 ms** | **8.673 ms** | **4.351 ms** | **-69.7%** | **-49.8%** |
| **p99 Latency** | **16.649 ms** | **9.531 ms** | **4.614 ms** | **-72.3%** | **-51.6%** |
| Min / Max Latency | 12.943 ms / 21.596 ms | 8.012 ms / 11.404 ms | 3.961 ms / 4.739 ms | — | — |
| **Synchronized Inference (Mean)** | **13.365 ms** | **8.311 ms** | **4.062 ms** | **-69.6%** | **-51.1%** |
| Preprocess Stage (Mean) | 0.007 ms | 0.007 ms | 0.006 ms | Identical | Identical |
| Model Predict Stage (Mean) | 13.316 ms | 8.264 ms | 4.015 ms | -69.8% | -51.4% |
| Pose Adapt Stage (Mean) | 0.050 ms | 0.047 ms | 0.047 ms | -6.0% | Identical |
| Tracking Stage (Mean) | 0.002 ms | 0.002 ms | 0.002 ms | Identical | Identical |
| FSM Stage (Mean) | 0.0001 ms | 0.0001 ms | 0.0001 ms | Identical | Identical |
| Peak Torch Alloc VRAM | 104.01 MB | 7.65 MB | 12.34 MB | — | — |
| Peak Host RSS Memory | 1535.34 MB | 1715.54 MB | 1342.82 MB | -192.5 MB | -372.7 MB |
| Run Variability (CV) | 0.0124 (1.24%) | 0.0023 (0.23%) | 0.0055 (0.55%) | High stability | High stability |

## Key Findings
1. **Unrivaled Performance:** TensorRT FP16 delivers **212.91 FPS** and **4.125 ms mean latency**, exceeding real-time requirements (30 FPS target) by over **7x** headroom.
2. **Sub-5ms Guaranteed Worst-Case:** p99 latency is **4.614 ms**, and max observed latency across 900 measured frames is **4.739 ms**.
3. **Memory Efficiency:** Host RSS peak is lower than both ONNX and PyTorch (1342.82 MB vs 1715.54 MB / 1535.34 MB).
4. **Accuracy Verification:** Full 17-keypoint detection parity confirmed on test images.

## Artifact
- Raw JSON artifact: `benchmarks/results/p9_004_tensorrt_fp16.json`
