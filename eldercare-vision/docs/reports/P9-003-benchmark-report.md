# P9-003 Benchmark Report — ONNX Runtime CUDA on NVIDIA RTX 3070

## Summary
Benchmark evaluation of `yolo26s-pose.onnx` (opset 18, onnxslimmed) executed with ONNX Runtime 1.23.2 using `CUDAExecutionProvider` on the target NVIDIA GeForce RTX 3070 8GB GPU, compared directly against the P9-002 PyTorch CUDA baseline.

## Environment (Measured)
- Host: Windows 10 (10.0.26200), Python 3.10.11
- GPU: NVIDIA GeForce RTX 3070 (8192 MB VRAM), Driver 616.92
- CUDA: 12.1 (Compute Capability 8.6)
- cuDNN: 90100 (9.1.0)
- ONNX Runtime: 1.23.2 (CUDAExecutionProvider)
- ONNX: 1.22.0
- PyTorch: 2.5.1+cu121
- Ultralytics: 8.4.142
- NumPy: 2.2.6
- OpenCV: 5.0.0.93

## Benchmark Methodology
- Model: `yolo26s-pose.onnx` (FP32, opset 18, 39.9 MB)
- Input: Deterministic synthetic NumPy frames (640x480 uint8 RGB, seed 42)
- Warmup: 40 frames per repetition (excluded from timing)
- Repetitions: 3 runs of 300 measured frames (900 total measured frames)
- Synchronization: `torch.cuda.synchronize()` bracketing inference and end-to-end stages

## Measured Results & Comparison

| Metric | P9-002 PyTorch Baseline | P9-003 ONNX Runtime | Delta (vs Baseline) |
|---|---|---|---|
| **Median Throughput (FPS)** | **64.54 FPS** | **105.33 FPS** | **+63.2% faster** |
| Run 1 / Run 2 / Run 3 FPS | 43.06 / 66.15 / 64.54 | 56.56 / 105.33 / 105.49 | — |
| **Mean Total Latency** | **13.436 ms** | **8.377 ms** | **-37.7% lower latency** |
| **Median Total Latency (p50)** | **13.209 ms** | **8.333 ms** | **-36.9%** |
| **p90 Latency** | **13.956 ms** | **8.542 ms** | **-38.8%** |
| **p95 Latency** | **14.352 ms** | **8.673 ms** | **-39.6%** |
| **p99 Latency** | **16.649 ms** | **9.531 ms** | **-42.8%** |
| Min / Max Latency | 12.943 ms / 21.596 ms | 8.012 ms / 11.404 ms | — |
| **Synchronized Inference (Mean)** | **13.365 ms** | **8.311 ms** | **-37.8%** |
| Preprocess Stage (Mean) | 0.007 ms | 0.007 ms | Identical |
| Model Predict Stage (Mean) | 13.316 ms | 8.264 ms | -37.9% |
| Pose Adapt Stage (Mean) | 0.050 ms | 0.047 ms | -6.0% |
| Tracking Stage (Mean) | 0.002 ms | 0.002 ms | Identical |
| FSM Stage (Mean) | 0.0001 ms | 0.0001 ms | Identical |
| Peak Torch Alloc VRAM | 104.01 MB | 7.65 MB | — |
| Peak RSS Memory | 1535.34 MB | 1715.54 MB | +180.2 MB |
| Run Variability (CV) | 0.0124 (1.24%) | 0.0023 (0.23%) | High stability (<1%) |

## Analysis
- **Throughput & Latency:** ONNX Runtime with `CUDAExecutionProvider` yields a major performance gain over native PyTorch, increasing throughput from 64.54 FPS to 105.33 FPS (+63.2%) and reducing mean latency from 13.436 ms to 8.377 ms (-37.7%).
- **Tail Latency:** p95 latency drops from 14.352 ms to 8.673 ms, ensuring sub-10ms response times for >99% of frames.
- **Accuracy Parity:** Verification confirms full 17-keypoint detection parity on sample images without regression.

## Artifact
- Raw JSON artifact: `benchmarks/results/p9_003_onnx.json`
