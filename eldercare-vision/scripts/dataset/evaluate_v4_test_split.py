"""P11.7-016: Final Independent Evaluation on Held-Out Test Split.

Evaluates the frozen V4 Fall Detection Pipeline on the 28 held-out test sequences
(subj-07 through subj-10) from the locked V4 Master Dataset Manifest.

Pipeline:
Real decoded video -> YOLO26s-Pose (CUDA) -> ByteTrack ->
Camera Perspective Normalizer -> Multi-Scale Temporal Features ->
GRUClassifierV4 (24 weights) -> ADL False-Alert Suppressor ->
TrackFallStateMachineV3 (with cooldown throttling).

Computes genuine empirical metrics:
Recall, Precision, Specificity, F1, F2, FAR/hour, Mean TTA, and FPS.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

# Add src directory to python path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eldercare.fall_engine.evaluation.metrics_v4 import (
    DeploymentMetricsV4,
    V4EvaluationResult,
    compute_deployment_metrics_v4,
)
from eldercare.fall_engine.learned_classifier.classifier_v4 import GRUClassifierV4
from eldercare.fall_engine.normalization.camera_normalizer import CameraNormalizationConfig
from eldercare.fall_engine.pipeline_v4 import FallEnginePipelineV4
from eldercare.fall_engine.state_machine.states import FallEvent, FallState
from eldercare.fall_engine.state_machine_v3.config_v3 import FallStateMachineConfigV3
from eldercare.fall_engine.suppression.adl_suppressor import ADLSuppressionConfig
from eldercare.vision.pose.adapter import adapt_pose_results
from eldercare.vision.tracking.observation import TrackObservation

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("evaluate_v4_test_split")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def sha256_file(path: Path | str, normalize_crlf: bool = False) -> str:
    """Compute SHA-256 hash of a file."""
    data = Path(path).read_bytes()
    if normalize_crlf:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def verify_freeze_manifest() -> dict[str, Any]:
    """Verify that all frozen artifacts match their cryptographic SHA-256 hashes."""
    manifest_path = ROOT / "models" / "v4_freeze_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Freeze manifest not found at {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel_path, meta in manifest["artifacts"].items():
        full_path = ROOT / rel_path
        if not full_path.is_file():
            raise RuntimeError(f"Frozen artifact missing on disk: {rel_path}")
        disk_hash = sha256_file(full_path)
        if disk_hash != meta["sha256"]:
            raise RuntimeError(
                f"Freeze manifest hash mismatch for {rel_path}: disk={disk_hash}, expected={meta['sha256']}"
            )
    LOG.info("All %d frozen artifacts verified cryptographically.", len(manifest["artifacts"]))
    return manifest


def load_urfd_fall_onsets(annotation_csv: Path) -> dict[str, dict[str, int]]:
    """Parse urfall-cam0-falls.csv for exact fall onset and lying frame indices."""
    onsets: dict[str, dict[str, int]] = {}
    if not annotation_csv.is_file():
        return onsets

    with open(annotation_csv, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 3:
                continue
            seq_id = row[0].strip()
            try:
                frame_num = int(row[1])
                label = int(row[2])
            except ValueError:
                continue

            if seq_id not in onsets:
                onsets[seq_id] = {"fall_start": 999999, "fall_end": -1, "lying_start": 999999}

            if label == 0:  # Falling
                onsets[seq_id]["fall_start"] = min(onsets[seq_id]["fall_start"], frame_num)
                onsets[seq_id]["fall_end"] = max(onsets[seq_id]["fall_end"], frame_num)
            elif label == 1:  # Lying on floor
                onsets[seq_id]["lying_start"] = min(onsets[seq_id]["lying_start"], frame_num)

    return onsets


def evaluate_sequence(
    video_path: Path,
    is_fall_gt: bool,
    stream_id: str,
    model: YOLO,
    pipeline: FallEnginePipelineV4,
    tracker_config_path: Path,
    fall_onset_frame: int | None = None,
) -> tuple[V4EvaluationResult, dict[str, Any]]:
    """Run frozen V4 pipeline on a single real recorded video."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    pipeline.reset_all()

    frame_idx = 0
    pose_available_frames = 0
    tracking_active_frames = 0
    alert_events: list[dict[str, Any]] = []
    first_alert_time: float | None = None
    frames_with_detections = 0

    fall_onset_time_sec = (fall_onset_frame / fps) if fall_onset_frame is not None else None
    t0_eval = time.perf_counter()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = frame_idx / fps
        h, w = frame.shape[:2]

        # 1. YOLO26s-Pose Inference with ByteTrack tracking
        res = model.track(
            source=frame,
            persist=True,
            tracker=str(tracker_config_path),
            verbose=False,
            imgsz=640,
            conf=0.25,
            device=0,
        )[0]

        pose_frame = adapt_pose_results(res)

        boxes = res.boxes
        assigned_track_ids: list[int | None] = []
        if boxes is not None and boxes.id is not None:
            assigned_track_ids = [int(tid) for tid in boxes.id.tolist()]
        else:
            assigned_track_ids = [None] * len(pose_frame.persons)

        if len(pose_frame.persons) > 0:
            pose_available_frames += 1
            frames_with_detections += 1

        for idx_p, person in enumerate(pose_frame.persons):
            tid = assigned_track_ids[idx_p] if idx_p < len(assigned_track_ids) else None
            if tid is None:
                tid = 1

            tracking_active_frames += 1

            # Build TrackObservation
            obs = TrackObservation(
                camera_id=stream_id,
                track_id=tid,
                timestamp=timestamp,
                bbox_xyxy=person.bbox_xyxy,
                detection_confidence=person.detection_confidence,
                keypoints=person.keypoints,
                image_width=w,
                image_height=h,
            )

            # Process through Unified V4 Pipeline
            state, event = pipeline.process_observation(obs)

            if event is not None:
                alert_events.append(
                    {
                        "frame_idx": frame_idx,
                        "timestamp": timestamp,
                        "track_id": tid,
                        "confidence": event.confidence,
                    }
                )
                if first_alert_time is None:
                    first_alert_time = timestamp

        frame_idx += 1

    cap.release()
    t_elapsed = time.perf_counter() - t0_eval
    actual_duration_sec = frame_idx / fps if fps > 0 else 0.0

    # Determine classification outcome
    alert_count = len(alert_events)
    tta_sec: float | None = None

    if is_fall_gt:
        if alert_count > 0 and first_alert_time is not None:
            is_tp = True
            is_fn = False
            is_fp = False
            is_tn = False
            false_alerts = max(0, alert_count - 1)
            onset_ref = fall_onset_time_sec if fall_onset_time_sec is not None else 0.0
            tta_sec = max(0.0, first_alert_time - onset_ref)
        else:
            is_tp = False
            is_fn = True
            is_fp = False
            is_tn = False
            false_alerts = 0
    else:
        if alert_count > 0:
            is_tp = False
            is_fn = False
            is_fp = True
            is_tn = False
            false_alerts = alert_count
        else:
            is_tp = False
            is_fn = False
            is_fp = False
            is_tn = True
            false_alerts = 0

    eval_result = V4EvaluationResult(
        stream_id=stream_id,
        is_fall=is_fall_gt,
        is_true_positive=is_tp,
        is_false_positive=is_fp,
        is_true_negative=is_tn,
        is_false_negative=is_fn,
        is_short_clip=True,
        is_long_form=False,
        declared_duration_seconds=actual_duration_sec,
        actual_decoded_frames=frame_idx,
        fps=fps,
        actual_processed_seconds=actual_duration_sec,
        time_to_alert_sec=tta_sec,
        is_duplicate_alert=len(alert_events) > 1,
        total_frames_in_fall_window=frame_idx,
        frames_with_usable_pose=pose_available_frames,
        expected_track_frames=frame_idx,
        continuous_track_frames=tracking_active_frames,
    )

    ledger_entry = {
        "stream_id": stream_id,
        "video_file": video_path.name,
        "is_fall_gt": is_fall_gt,
        "ground_truth_class": "FALL" if is_fall_gt else "ADL",
        "predicted_class": "FALL" if alert_count > 0 else "ADL",
        "classification": "TP" if is_tp else ("FN" if is_fn else ("FP" if is_fp else "TN")),
        "alert_count": alert_count,
        "first_alert_time_sec": first_alert_time,
        "fall_onset_time_sec": fall_onset_time_sec,
        "tta_sec": tta_sec,
        "total_frames": frame_idx,
        "duration_sec": actual_duration_sec,
        "eval_time_sec": t_elapsed,
        "fps": (frame_idx / t_elapsed) if t_elapsed > 0 else 0.0,
        "pose_availability_pct": (pose_available_frames / frame_idx * 100.0) if frame_idx > 0 else 0.0,
        "tracking_continuity_pct": (tracking_active_frames / frame_idx * 100.0) if frame_idx > 0 else 0.0,
        "alert_events": alert_events,
    }

    return eval_result, ledger_entry


def run_v4_test_evaluation(
    output_json_path: Path = ROOT / "docs" / "reports" / "P11.7-016-v4-test-evaluation.json",
) -> dict[str, Any]:
    """Execute final independent evaluation on the 28 held-out test sequences."""
    verify_freeze_manifest()

    # Load master manifest
    manifest_path = ROOT / "datasets" / "manifests" / "v4_multi_source_manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    test_records = [r for r in manifest_data["records"] if r.get("split") == "test"]

    LOG.info("Loaded %d held-out test split records from master manifest.", len(test_records))
    assert len(test_records) == 28, f"Expected 28 test records, got {len(test_records)}"

    # Load onsets
    urfd_onsets = load_urfd_fall_onsets(ROOT / "datasets" / "raw" / "urfd" / "urfall-cam0-falls.csv")

    # Load YOLO model
    model = YOLO("yolo26s-pose.pt")

    # Load frozen V4 classifier & config
    classifier = GRUClassifierV4.load(ROOT / "models" / "temporal_fall_classifier_v4.json")
    
    # Load calibrated YAML config
    with open(ROOT / "config" / "fall_detection_v4.yaml", encoding="utf-8") as f:
        yaml_cfg = yaml.safe_load(f)

    # Build Pipeline
    config_v3 = FallStateMachineConfigV3(
        use_learned_classifier=True,
        classifier_trigger_threshold=float(yaml_cfg.get("classifier_trigger_threshold", 0.68)),
        classifier_confirmation_threshold=float(yaml_cfg.get("classifier_confirmation_threshold", 0.69)),
        classifier_veto_threshold=float(yaml_cfg.get("classifier_veto_threshold", 0.55)),
        enable_adl_suppression=True,
        enable_track_stitching=True,
    )
    cam_config = CameraNormalizationConfig(
        camera_pitch_deg=25.0,
        camera_height_meters=2.4,
        enabled=True,
    )
    supp_config = ADLSuppressionConfig(
        classifier_veto_threshold=float(yaml_cfg.get("classifier_veto_threshold", 0.55)),
        enabled=True,
    )
    pipeline = FallEnginePipelineV4(
        config=config_v3,
        camera_config=cam_config,
        suppression_config=supp_config,
        classifier=classifier,
    )

    tracker_cfg = ROOT / "config" / "bytetrack_v3.yaml"
    if not tracker_cfg.is_file():
        tracker_cfg = ROOT / "eldercare-vision" / "config" / "bytetrack_v3.yaml"

    results: list[V4EvaluationResult] = []
    ledger: list[dict[str, Any]] = []

    LOG.info("Starting one-shot evaluation on 28 held-out test sequences...")
    t_start = time.perf_counter()

    for idx, rec in enumerate(test_records, start=1):
        vid_path = ROOT / rec["path_local"]
        if not vid_path.is_file():
            # Fallback path search
            vid_path = ROOT / "datasets" / "raw" / "urfd" / Path(rec["path_local"]).name

        stream_id = rec["sample_id"]
        is_fall = rec["is_fall"]
        seq_id = rec["sequence_id"]

        fall_onset = None
        if is_fall and seq_id in urfd_onsets:
            fall_onset = urfd_onsets[seq_id]["fall_start"]

        LOG.info("[%d/28] Evaluating %s (%s, fall_gt=%s)...", idx, stream_id, rec["activity"], is_fall)
        eval_res, ledger_res = evaluate_sequence(
            video_path=vid_path,
            is_fall_gt=is_fall,
            stream_id=stream_id,
            model=model,
            pipeline=pipeline,
            tracker_config_path=tracker_cfg,
            fall_onset_frame=fall_onset,
        )
        results.append(eval_res)
        ledger.append(ledger_res)

    total_time = time.perf_counter() - t_start
    metrics = compute_deployment_metrics_v4(results)

    fall_seqs = sum(1 for r in results if r.is_fall)
    adl_seqs = sum(1 for r in results if not r.is_fall)

    # Compile evaluation artifact
    eval_artifact: dict[str, Any] = {
        "evaluation_name": "V4-Final-Real-HeldOut-Test-Evaluation",
        "phase": "11.7",
        "task": "P11.7-016",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_wall_time_seconds": total_time,
        "overall_evaluation_fps": (metrics.actual_decoded_frames / total_time) if total_time > 0 else 0.0,
        "metrics": metrics.to_dict(),
        "summary_counts": {
            "total_sequences": len(results),
            "fall_sequences": fall_seqs,
            "adl_sequences": adl_seqs,
            "true_positives": metrics.tp,
            "false_positives": metrics.fp,
            "true_negatives": metrics.tn,
            "false_negatives": metrics.fn,
        },
        "per_sequence_ledger": ledger,
    }

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(eval_artifact, indent=2), encoding="utf-8")
    LOG.info("Saved final test evaluation results to %s", output_json_path)

    # Print summary table
    print("\n" + "=" * 85)
    print("PHASE 11.7 (P11.7-016) — V4 FINAL HELD-OUT TEST EVALUATION SUMMARY")
    print("=" * 85)
    print(f"Sequences Evaluated   : {metrics.total_sequences} (Falls: {fall_seqs}, ADLs: {adl_seqs})")
    print(f"Confusion Matrix      : TP={metrics.tp}, FP={metrics.fp}, TN={metrics.tn}, FN={metrics.fn}")
    print("-" * 85)
    print(f"Recall (Sensitivity)  : {metrics.recall * 100:.2f}%")
    print(f"Precision (PPV)       : {metrics.precision * 100:.2f}%")
    print(f"F1-Score              : {metrics.f1_score:.4f}")
    print(f"F2-Score (Recall-pref): {metrics.f2_score:.4f}")
    print(f"Accuracy              : {metrics.accuracy * 100:.2f}%")
    print("-" * 85)
    print(f"ADL False Alerts      : {metrics.short_clip_adl_fp_count} / {metrics.short_clip_adl_total_count} ({metrics.short_clip_adl_fp_rate * 100:.2f}%)")
    print(f"False Alert Rate / hr : {metrics.long_form_false_alerts_per_camera_hour:.2f} FA/hr")
    print(f"Median Time-to-Alert  : {metrics.median_tta_sec:.3f} s")
    print(f"Average Throughput    : {metrics.throughput_fps:.2f} FPS")
    print("=" * 85 + "\n")

    return eval_artifact


if __name__ == "__main__":
    run_v4_test_evaluation()
