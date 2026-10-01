# Risk Register — ElderCare Vision

| ID | Risk | Likelihood | Impact | Mitigation | Verification |
|---|---|---|---|---|---|
| R-001 | Missed fall | Medium | High | prioritize Recall, temporal tuning, scenario analysis | false-negative review |
| R-002 | False alert | High | Medium/High | multi-signal confirmation, persistence, cooldown | false alerts/hour |
| R-003 | Normal lying interpreted as fall | Medium | High | require rapid transition evidence, not posture only | lying/sitting UAT |
| R-004 | Pose keypoints fail under occlusion | High | Medium/High | confidence-aware rules, track history, uncertain state | occlusion tests |
| R-005 | Low light reduces pose quality | Medium | High | characterize limits; camera placement guidance | low-light tests |
| R-006 | Camera disconnect | Medium | High | heartbeat/stall detection + bounded reconnect | failure injection |
| R-007 | Wi-Fi jitter | High | Medium | decouple capture/inference; frame dropping policy | network impairment test |
| R-008 | Frame backlog increases latency | Medium | High | bounded latest-frame queue | queue/latency telemetry |
| R-009 | Tracker ID switch | Medium | Medium | ByteTrack tuning; conservative state transfer | multi-person test |
| R-010 | Agent/VLM hallucination | Medium | High | label as context; never override core detector | adversarial review |
| R-011 | Agent provider outage | Medium | Medium | async queue, timeout, retry, failure event | provider-offline test |
| R-012 | MQTT outage | Medium | Low/Medium | non-blocking publisher/retry | broker-offline test |
| R-013 | Database unavailable | Low/Medium | High | retry/backoff; explicit degraded mode | DB failure test |
| R-014 | GPU OOM | Low/Medium | High | s-pose default, bounded batch=1, memory telemetry | stress test |
| R-015 | Performance below target | Medium | Medium | TensorRT FP16; n-pose fallback | benchmark |
| R-016 | Dataset leakage | Medium | High | sequence/subject-disjoint split | split audit |
| R-017 | Dataset bias/generalization | High | High | multiple datasets + local held-out data | cross-dataset eval |
| R-018 | Dataset licensing violation | Low | High | source manifest; no redistribution | repository audit |
| R-019 | Privacy exposure | Medium | High | local-first; minimal evidence; retention; consent | privacy checklist |
| R-020 | Credentials leak | Medium | High | env secrets + redaction + secret scan | CI/security review |
| R-021 | Scope creep | High | Medium | phase gates + backlog | implementation review |
| R-022 | Benchmark cherry-picking | Medium | High | fixed scripts/config and raw outputs | reproducibility check |
| R-023 | Unsafe real-world interpretation | Medium | High | clearly label as POC, not medical/emergency guarantee | docs review |
