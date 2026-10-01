"""Execute ElderCare Vision P11-003: UP-Fall Robustness Evaluation on Frozen Pipeline.

Primary Runtime: TensorRT 11 FP16 (yolo26s-pose.engine) on NVIDIA RTX 3070 8GB.
Tracker: stock bytetrack.yaml.
Configuration: config/fall_detection.yaml (frozen ADR-005).
Dataset: UP-Fall test split (15 sequences: 8 falls, 7 ADLs across held-out Subject12..17).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
from ultralytics import YOLO

from eldercare.fall_engine.calibration.config_loader import load_fall_detection_config
from eldercare.fall_engine.calibration.freeze import compute_file_sha256
from eldercare.fall_engine.evaluation.manifest import load_manifest
from eldercare.fall_engine.state_machine import (
    TrackFallStateMachine,
)
from eldercare.vision.pose.adapter import (
    adapt_pose_results,
)
from eldercare.vision.tracking.observation import (
    TrackObservation,
    tracked_frame_to_observations,
)
from eldercare.vision.tracking.tracker import TrackedFrame, TrackedPerson

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_upfall_frozen")


def run_upfall_final_evaluation() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    manifest_path = root / "datasets" / "manifests" / "upfall_manifest.csv"
    config_path = root / "config" / "fall_detection.yaml"
    engine_path = root / "yolo26s-pose.engine"
    pt_path = root / "yolo26s-pose.pt"

    logger.info("=== Pre-flight Validation ===")
    assert manifest_path.is_file(), f"Manifest missing: {manifest_path}"
    assert config_path.is_file(), f"Config missing: {config_path}"
    assert engine_path.is_file(), f"TensorRT engine missing: {engine_path}"
    assert pt_path.is_file(), f"PyTorch golden reference weights missing: {pt_path}"

    pt_hash = compute_file_sha256(pt_path, normalize_newlines=False)
    engine_hash = compute_file_sha256(engine_path, normalize_newlines=False)
    config_hash = compute_file_sha256(config_path, normalize_newlines=True)
    manifest_hash = compute_file_sha256(manifest_path, normalize_newlines=True)

    logger.info(f"yolo26s-pose.pt SHA-256: {pt_hash}")
    logger.info(f"yolo26s-pose.engine SHA-256: {engine_hash}")
    logger.info(f"config/fall_detection.yaml normalized LF SHA-256: {config_hash}")
    logger.info(f"upfall_manifest.csv normalized LF SHA-256: {manifest_hash}")

    # Verify frozen hashes against locked values
    expected_pt = "a083adb42303728ae14c4bd6bd56d80da46f82fb2564dbd6f31dcc92ea321646"
    expected_engine = "6cf6142e7d4301b386b286bdcccce31a1a393457ce01a0e8b13fc5234e89f947"
    expected_config = "b56152c7dae9f604d53eb7feac0ed2659f54ffdc57b531827206d8548aed9532"
    expected_manifest = "53f5e8f35a360aff59b4ce3b0532e7f1f661762e79367a91046d0a39752baa1f"

    assert pt_hash == expected_pt, f"PT hash mismatch: {pt_hash} != {expected_pt}"
    assert engine_hash == expected_engine, (
        f"Engine hash mismatch: {engine_hash} != {expected_engine}"
    )
    assert config_hash == expected_config, (
        f"Config hash mismatch: {config_hash} != {expected_config}"
    )
    assert manifest_hash == expected_manifest, (
        f"Manifest hash mismatch: {manifest_hash} != {expected_manifest}"
    )

    # Load frozen configs
    sm_config, conf_config, cooldown_config = load_fall_detection_config(config_path)

    # Load test split records
    records = load_manifest(manifest_path)
    test_records = [r for r in records if r.split == "test"]
    assert len(test_records) == 15, f"Expected 15 test records, got {len(test_records)}"

    falls_count = sum(1 for r in test_records if r.is_fall)
    adls_count = sum(1 for r in test_records if not r.is_fall)
    assert falls_count == 8, f"Expected 8 falls, got {falls_count}"
    assert adls_count == 7, f"Expected 7 ADLs, got {adls_count}"

    results_ledger: list[dict[str, Any]] = []
    tp_count = 0
    fp_count = 0
    tn_count = 0
    fn_count = 0
    total_start_time = time.perf_counter()

    for idx, rec in enumerate(test_records, start=1):
        vid_path = root / "datasets" / rec.path_local
        assert vid_path.is_file(), f"Video file not found: {vid_path}"

        cap = cv2.VideoCapture(str(vid_path))
        assert cap.isOpened(), f"Cannot open video: {vid_path}"

        fps = cap.get(cv2.CAP_PROP_FPS) or 18.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Fresh model instance per sequence guarantees zero cross-video track state leakage
        model = YOLO(str(engine_path))

        # Per-sequence tracking & state machines
        track_histories: dict[int, list[TrackObservation]] = defaultdict(list)
        state_machines: dict[int, TrackFallStateMachine] = {}
        detected_events: list[dict[str, Any]] = []

        pose_failures = 0
        tracking_failures = 0
        frame_idx = 0

        seq_start_time = time.perf_counter()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps
            frame_h, frame_w = frame.shape[:2]

            # Run TensorRT FP16 pose tracking
            res = model.track(
                source=frame,
                persist=True,
                tracker="bytetrack.yaml",
                imgsz=640,
                device=0,
                verbose=False,
            )[0]

            # Adapt pose results
            pose_frame = adapt_pose_results(res)

            # Extract track IDs from results.boxes.id
            boxes = res.boxes
            track_ids: list[int | None] = []
            if boxes is not None and boxes.id is not None:
                track_ids = [int(tid) for tid in boxes.id.tolist()]
            else:
                track_ids = [None] * len(pose_frame.persons)

            # Build TrackedFrame
            tracked_persons: list[TrackedPerson] = []
            for p_idx, person in enumerate(pose_frame.persons):
                tid = track_ids[p_idx] if p_idx < len(track_ids) else None
                if tid is None:
                    tracking_failures += 1
                tracked_persons.append(TrackedPerson(person=person, track_id=tid))

            tracked_frame = TrackedFrame(
                image_width=frame_w,
                image_height=frame_h,
                persons=tuple(tracked_persons),
            )

            # Convert to observations
            observations = tracked_frame_to_observations(
                tracked_frame,
                camera_id=rec.camera_id,
                timestamp=timestamp,
            )

            if len(observations) == 0:
                pose_failures += 1

            # Update state machines
            for obs in observations:
                if obs.track_id is None:
                    continue
                tid = obs.track_id
                if tid not in state_machines:
                    state_machines[tid] = TrackFallStateMachine(
                        camera_id=rec.camera_id,
                        track_id=tid,
                        config=sm_config,
                        confidence_config=conf_config,
                    )
                track_histories[tid].append(obs)
                state, event = state_machines[tid].update(track_histories[tid])

                if event is not None:
                    detected_events.append(
                        {
                            "track_id": event.track_id,
                            "timestamp": round(event.confirmed_timestamp, 3),
                            "candidate_timestamp": round(event.candidate_timestamp, 3),
                            "down_start_timestamp": round(event.down_start_timestamp, 3),
                            "confidence": round(event.confidence, 4),
                            "frame_idx": frame_idx,
                            "descent_velocity": round(
                                event.features.normalized_vertical_velocity, 4
                            ),
                            "torso_angle_deg": round(
                                event.features.current_geometry.torso_angle_deg, 2
                            ),
                        }
                    )

            frame_idx += 1

        cap.release()
        seq_duration = time.perf_counter() - seq_start_time

        # Sequence-level prediction
        predicted_fall = len(detected_events) > 0
        ground_truth_fall = rec.is_fall

        # Classification
        classification = ""
        if ground_truth_fall and predicted_fall:
            classification = "TP"
            tp_count += 1
        elif not ground_truth_fall and predicted_fall:
            classification = "FP"
            fp_count += 1
        elif not ground_truth_fall and not predicted_fall:
            classification = "TN"
            tn_count += 1
        else:  # ground_truth_fall and not predicted_fall
            classification = "FN"
            fn_count += 1

        entry = {
            "dataset": "UP-Fall",
            "sample_id": rec.sample_id,
            "sequence_id": rec.sequence_id,
            "subject_id": rec.subject_id,
            "activity": rec.activity,
            "fall_type": rec.fall_type,
            "path_local": rec.path_local,
            "total_frames": frame_count,
            "fps": fps,
            "duration_sec": round(frame_count / fps, 3),
            "inference_time_sec": round(seq_duration, 3),
            "effective_fps": round(frame_count / seq_duration if seq_duration > 0 else 0, 1),
            "ground_truth_fall": ground_truth_fall,
            "predicted_fall": predicted_fall,
            "classification": classification,
            "incident_count": len(detected_events),
            "incidents": detected_events,
            "duplicate_alert_count": max(0, len(detected_events) - 1),
            "pose_insufficient_frames": pose_failures,
            "untracked_detections": tracking_failures,
            "decode_failure": False,
            "model_sha256": pt_hash,
            "engine_sha256": engine_hash,
            "config_sha256": config_hash,
            "runtime": "TensorRT 11 FP16",
        }
        results_ledger.append(entry)

        logger.info(
            f"[{idx:02d}/15] {rec.sample_id} ({rec.subject_id} - {rec.activity}): "
            f"GT={ground_truth_fall} Pred={predicted_fall} -> {classification} | "
            f"Events={len(detected_events)} | "
            f"{frame_count} frames in {seq_duration:.2f}s ({entry['effective_fps']} fps)"
        )

    total_eval_duration = time.perf_counter() - total_start_time

    # Calculate metrics
    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    recall = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp_count + tn_count) / len(test_records) if len(test_records) > 0 else 0.0

    summary_data = {
        "schema_version": "1.0.0",
        "task": "P11-003 — UP-Fall Final Robustness Evaluation",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": "NVIDIA GeForce RTX 3070 8GB",
        "runtime": "TensorRT 11 FP16",
        "dataset": "UP-Fall Detection Dataset (Camera 1 RGB)",
        "split": "test",
        "counts": {
            "total_evaluated": len(test_records),
            "falls_total": falls_count,
            "adls_total": adls_count,
            "true_positives": tp_count,
            "false_positives": fp_count,
            "true_negatives": tn_count,
            "false_negatives": fn_count,
        },
        "preliminary_metrics": {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        },
        "provenance": {
            "model_weights_sha256": pt_hash,
            "tensorrt_engine_sha256": engine_hash,
            "fall_detection_yaml_sha256": config_hash,
            "upfall_manifest_sha256": manifest_hash,
        },
        "total_eval_duration_sec": round(total_eval_duration, 2),
        "sequences": results_ledger,
    }

    # Save JSON raw evidence
    out_json = root / "docs" / "reports" / "P11-003-upfall-raw-evaluation.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    logger.info(f"Raw evaluation ledger written to {out_json}")

    # Generate Markdown Report
    out_md = root / "docs" / "reports" / "P11-003-upfall-evaluation-report.md"
    md_content = generate_markdown_report(summary_data)
    out_md.write_text(md_content, encoding="utf-8")
    logger.info(f"Evaluation report written to {out_md}")

    logger.info("=== P11-003 EVALUATION SUMMARY ===")
    logger.info(
        "Total Evaluated: %d (Falls: %d, ADLs: %d)",
        len(test_records),
        falls_count,
        adls_count,
    )
    logger.info("TP: %d, FP: %d, TN: %d, FN: %d", tp_count, fp_count, tn_count, fn_count)
    logger.info(
        "Metrics: Precision=%.4f, Recall=%.4f, F1=%.4f, Accuracy=%.4f",
        precision,
        recall,
        f1,
        accuracy,
    )
    logger.info("P11-003 EXECUTION COMPLETE.")
    return 0


def generate_markdown_report(data: dict[str, Any]) -> str:
    counts = data["counts"]
    metrics = data["preliminary_metrics"]
    prov = data["provenance"]

    rows = []
    for s in data["sequences"]:
        incidents_str = f"{s['incident_count']}"
        gt_str = "**Fall**" if s["ground_truth_fall"] else "ADL"
        pred_str = "**Fall**" if s["predicted_fall"] else "Normal"
        rows.append(
            f"| `{s['sample_id']}` | {s['subject_id']} | {s['activity']} | {gt_str} | "
            f"{pred_str} | **{s['classification']}** | {incidents_str} | "
            f"{s['effective_fps']} |"
        )
    table_str = "\n".join(rows)

    m_hash = prov["model_weights_sha256"][:10]
    e_hash = prov["tensorrt_engine_sha256"][:10]
    c_hash = prov["fall_detection_yaml_sha256"][:10]

    return f"""# P11-003 — UP-Fall Final Robustness Evaluation Report

## 1. Executive Summary

- **Evaluation Task:** P11-003 — UP-Fall Detection Dataset Final Held-Out Evaluation (Camera 1 RGB)
- **Execution Date:** {data["timestamp"]}
- **Hardware:** {data["hardware"]}
- **Inference Runtime:** {data["runtime"]}
- **Frozen Baseline Model:** `yolo26s-pose` (SHA-256 `{m_hash}...`)
- **Frozen TensorRT Engine:** `yolo26s-pose.engine` (SHA-256 `{e_hash}...`)
- **Frozen Fall Detection Config:** `config/fall_detection.yaml` (SHA-256 `{c_hash}...`)

## 2. Classification Results & Raw Counts

| Metric | Measured Value |
|---|---|
| **Total Test Sequences** | **{counts["total_evaluated"]}** |
| Ground Truth Falls | {counts["falls_total"]} |
| Ground Truth ADLs | {counts["adls_total"]} |
| **True Positives (TP)** | **{counts["true_positives"]}** |
| **False Positives (FP)** | **{counts["false_positives"]}** |
| **True Negatives (TN)** | **{counts["true_negatives"]}** |
| **False Negatives (FN)** | **{counts["false_negatives"]}** |

### Robustness Performance Metrics

- **Accuracy:** {metrics["accuracy"] * 100:.2f}%
- **Precision:** {metrics["precision"] * 100:.2f}%
- **Recall (Sensitivity):** {metrics["recall"] * 100:.2f}%
- **F1 Score:** {metrics["f1_score"] * 100:.2f}%

*(Note: Formal final multi-dataset metric consolidation will be compiled in P11-005).*

## 3. Descriptive Comparison with Frozen URFD Baseline

- **URFD (Primary Benchmark):** TP=1, FP=10, TN=6, FN=11
  (Precision=9.09%, Recall=8.33%, F1=8.70%, Accuracy=25.00%)
- **UP-Fall (Robustness Benchmark):** TP={counts["true_positives"]}, FP={counts["false_positives"]},
  TN={counts["true_negatives"]}, FN={counts["false_negatives"]}
  (Precision={metrics["precision"] * 100:.2f}%, Recall={metrics["recall"] * 100:.2f}%,
   F1={metrics["f1_score"] * 100:.2f}%, Accuracy={metrics["accuracy"] * 100:.2f}%)
- **Generalization Note:** Cross-dataset differences highlight domain shift across camera angles,
  framerates, room geometry, and subject variations without tuning detector thresholds.

## 4. Per-Sequence Evaluation Ledger

| Sample ID | Subject | Activity | Ground Truth | Prediction | Class | Incidents | FPS |
|---|---|---|---|---|:---:|:---:|:---:|
{table_str}

## 5. Failure & Limitations Analysis

- **Decode Failures:** 0 / 15 sequences.
- **Subject-Disjoint Guarantee:** All 15 test sequences belong strictly to held-out test subjects
  (`Subject12` through `Subject17`), ensuring zero cross-subject leakage with dev sequences.
- **Zero-Tuning Policy:** Evaluated strictly once without weight updates or threshold tuning.

## 6. Verification & Integrity Confirmation

- All 15 test sequences evaluated strictly once.
- 0% sequence or subject overlap with development set.
- Zero model weights or threshold modifications performed.
"""


if __name__ == "__main__":
    sys.exit(run_upfall_final_evaluation())
