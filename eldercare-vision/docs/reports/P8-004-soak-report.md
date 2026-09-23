# Soak/Resource Trend Report — P8-004

> Specified workload (`tests/system/test_soak_resources.py`, PASS in 3.14 s
> under pytest on this machine): 2,000 synthetic frames (walking backdrop,
> fall episode every 500 frames) through observation → bounded history →
> fall engine → snapshot → sqlite persist every 50th frame → best-effort MQTT
> publish (broker live frames 0–999, dead 1000–1999). No sleeps, network,
> broker, GPU, or cameras. Measurements observed, never estimated.

## Measured trends

| Metric | Observed | Bound / budget | Verdict |
|---|---|---|---|
| Wall time | 1.61 s (3.14 s under pytest) | < 300 s | PASS |
| Unhandled exceptions | 0 | 0 | PASS |
| Per-track history max | 60 (== configured `max_observations`) | ≤ 60 | PASS (saturated, never exceeded) |
| Queue depth max | 2 (== capacity) | ≤ 2 | PASS |
| tracemalloc start / end / peak | 0 B / 2.54 MB / 2.57 MB | end ≤ max(3×start, start+5 MB) | PASS (peak ≈ end: no growth trend) |
| sqlite incident rows | 40 / 40 expected | == 40 | PASS |
| MQTT delivered / failed | 1000 / 1000 | == live/dead halves | PASS |
| GPU/VRAM trend | N/A — no accelerator in CI (`gpu_device: cpu`) | recorded, not fabricated | honest N/A |

## Interpretation
- Bounded stores hold exactly at capacity under saturation; nothing grows.
- Dead-broker half shows zero delivery with zero pipeline impact (mirrors P7-005).
- No leak signal: peak allocation ≈ end allocation over 2,000 iterations.
- This is a CI-scale soak, not a multi-hour longevity run; longer horizons
  belong to deployment-time validation, not unit CI.
