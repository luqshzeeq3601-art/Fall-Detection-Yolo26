# ADR-005 — Freeze Fall Engine Dataset Splits and Detector Configuration

- **Status:** Accepted
- **Date:** 2026-09-23
- **Deciders:** VISION, EVAL, DOC, Muse COORD

## Context

Scientific integrity in computer vision and fall detection systems requires strict separation between hyperparameter calibration and final benchmark evaluation. Following Phase 4 threshold calibration on the development split (P4-007), all dataset manifests and detector configurations must be immutably frozen prior to Phase 11 final evaluation.

Without an explicit cryptographic freeze and automated checksum verification, there is risk of accidental data leakage, test split tampering, or post-hoc threshold tweaking (data snooping / p-hacking) to inflate test metrics.

## Decision

Freeze the dataset split manifests and fall detector configuration at Phase 4 closure, recording their canonical SHA-256 cryptographic digests:

| File Path | SHA-256 Digest (Normalized LF) | Description |
|---|---|---|
| `config/fall_detection.yaml` | `b56152c7dae9f604d53eb7feac0ed2659f54ffdc57b531827206d8548aed9532` | Calibrated fall engine thresholds, confidence weights, cooldowns, and partition metadata |
| `datasets/manifests/urfd_manifest.csv` | `6df450e36b2d6309b5aaa4133e6dcc28b4d51cb17ca5eacff93549f4a3134cb1` | Primary temporal benchmark manifest (70 sequences: 30 fall, 40 ADL; dev/test subject disjoint) |
| `datasets/manifests/upfall_manifest.csv` | `53f5e8f35a360aff59b4ce3b0532e7f1f661762e79367a91046d0a39752baa1f` | Secondary multi-activity benchmark manifest (40 sequences: 20 fall, 20 ADL; dev/test disjoint) |
| `datasets/manifests/local_manifest.csv` | `3bc17a1e73efba5526c821d49d0b76a60ca74c7d499e076eefc2d997c4e7f053` | Local domain UAT recording manifest (12 sequences: 4 fall, 8 ADL; dev/test disjoint) |

## Implementation & Verification Rules

1. All future evaluation pipelines (including Phase 11 final benchmark runs) must programmatically verify that these artifacts match the frozen SHA-256 digests before running.
2. Any proposed modification to thresholds, weights, or dataset split boundaries requires an explicit superseding ADR and review gate approval.
3. Automated unit tests in `tests/unit/test_frozen_splits_and_config.py` assert checksum invariance as part of regular CI.

## Consequences

- **Guaranteed Test Integrity:** Zero test set contamination or post-calibration split adjustment.
- **Reproducibility:** Experiments and benchmarks remain 100% reproducible across machines and environments.
- **Clean Handoff:** Enables confident progression through Phase 5–10 knowing detection thresholds and evaluation baselines are locked.
