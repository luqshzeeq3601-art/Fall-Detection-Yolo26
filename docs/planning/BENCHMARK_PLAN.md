# Benchmark Plan — RTX 3070

## 1. Goal

Measure the real end-to-end performance of ElderCare Vision on the target NVIDIA RTX 3070 and choose the deployment runtime based on evidence.

## 2. Model variants

Required:

- `yolo26s-pose.pt` — default
- `yolo26n-pose.pt` — fallback comparison

Optional:

- `yolo26m-pose.pt` — accuracy/performance comparison only

## 3. Runtime variants

Benchmark:

1. PyTorch
2. ONNX
3. TensorRT FP16

Optional:

4. OpenVINO CPU as non-NVIDIA fallback

Do not prioritize OpenVINO for RTX 3070 GPU deployment.

## 4. Test conditions

Keep constant:

- same source video,
- same resolution,
- same `imgsz=640`,
- same confidence settings,
- same tracker,
- same temporal engine,
- same machine state where practical,
- warmup before measurement,
- batch size 1 for live stream.

## 5. Measurements

### Model/runtime

- pose inference p50/p95 ms
- processed FPS
- GPU utilization
- GPU VRAM
- CPU utilization
- RAM
- model load time

### Full pipeline

- decoded frame → pose complete
- decoded frame → tracking complete
- decoded frame → fall-engine result
- dropped frames
- queue depth
- incident persistence latency
- WebSocket notification latency

## 6. Benchmark procedure

For each variant:

1. record environment versions,
2. load model,
3. warm up,
4. process the fixed benchmark clip,
5. exclude warmup samples,
6. capture per-frame timings,
7. capture resource samples,
8. run at least three repetitions,
9. report median plus p50/p95 distributions,
10. save raw results.

## 7. Acceptance logic

Default stays `yolo26s-pose.pt` if:

- complete pipeline >=15 FPS,
- vision-loop p95 <=100 ms,
- no stability/OOM issue.

Consider `yolo26n-pose.pt` if:

- default cannot meet latency/FPS after reasonable TensorRT optimization,
- accuracy trade-off is reported.

Consider `yolo26m-pose.pt` only if:

- it still meets system gates,
- its fall-level evaluation materially improves,
- the improvement is reproducible.

## 8. TensorRT

Primary target:

```text
TensorRT FP16
```

Reason:

- target GPU is NVIDIA,
- Ultralytics supports TensorRT export,
- FP16 usually provides an appropriate deployment path without INT8 calibration complexity.

Exact performance must be measured locally.

## 9. Result table template

| Model | Runtime | Precision | Recall | F1 | FPS | Inference p95 | Vision p95 | VRAM | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| yolo26s-pose | PyTorch | TBD | TBD | TBD | TBD | TBD | TBD | TBD | baseline |
| yolo26s-pose | TensorRT FP16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | primary |
| yolo26n-pose | TensorRT FP16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | fallback |

## 10. Integrity rule

Never put benchmark numbers in README/resume unless they can be reproduced from a saved benchmark run.
