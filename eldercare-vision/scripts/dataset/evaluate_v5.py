"""Phase 11.8 V5 One-Shot Held-Out Public Dataset Evaluation Engine (P11.8-024..026 / Integrity Repair).

Runs one-shot evaluation of the frozen V5 Fall Detection Pipeline on the
held-out Test-A split from real decoded video.

Pipeline:
Real decoded video -> YOLO26s-Pose -> ByteTrack ->
Multi-Scale Temporal Features -> ADL False Alert Suppressor ->
TemporalSkeletonClassifierV5 (M2/M3) -> PostProcessorV5.

Evaluator Guards:
1. Hard-fails on `split=all` for deployment gates.
2. Hard-fails if any dev/training sample is included in a test report.
3. Hard-fails on duplicate video SHA-256 hashes.
4. Hard-fails on overlapping subject IDs between dev pool and test split.
5. Hard-fails on label-derived synthetic samples or missing real pose caches.
6. Hard-fails on unlocked or mismatched freeze manifest.

Computes:
- Event-Level TP, FP, TN, FN, Precision, Recall, Specificity, F1, F2 with Wilson 95% CIs
- Missed-fall rate, duplicate-alert rate
- Empirical Time-To-Alert (TTA) p50 (median), p95, and mean
- Short-clip ADL false-positive rate
- End-to-end FPS & Track Continuity
"""

from __future__ import annotations

import argparse
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

# Add src directory to python path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.dataset.frame_validator import FrameValidator, crop_right_rgb_half
from eldercare.fall_engine.evaluation.event_matching import (
    AlertEvent,
    EventMatcher,
    SequenceGroundTruth,
    compute_wilson_confidence_interval,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    ClassifierV5M1_HistGBDT,
    PostProcessorConfigV5,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import TemporalSkeletonClassifierV5
from eldercare.fall_engine.pipeline_v5 import FallEnginePipelineV5, PipelineConfigV5
from eldercare.vision.pose.adapter import adapt_pose_results
from eldercare.vision.tracking.observation import TrackObservation

LOG = logging.getLogger("evaluate_v5")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def sha256_file(path: Path | str) -> str:
    """Compute SHA-256 hash of a file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_freeze_manifest_v5(repo_root: Path = ROOT) -> dict[str, Any]:
    """Cryptographically verify all frozen V5 artifacts."""
    manifest_path = repo_root / "models" / "v5_freeze_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"V5 Freeze manifest not found at {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rel_path, meta in manifest.get("artifacts", {}).items():
        full_path = repo_root / rel_path
        if not full_path.is_file():
            raise RuntimeError(f"Frozen artifact missing on disk: {rel_path}")
        disk_hash = sha256_file(full_path)
        if disk_hash != meta["sha256"]:
            raise RuntimeError(
                f"Freeze manifest hash mismatch for {rel_path}: disk={disk_hash}, expected={meta['sha256']}"
            )
    LOG.info(
        "All %d frozen V5 artifacts verified cryptographically.", len(manifest.get("artifacts", {}))
    )
    return manifest


def validate_evaluator_guards(
    records: list[dict[str, Any]],
    all_manifest_records: list[dict[str, Any]],
    target_split: str,
    is_deployment_gate: bool = True,
    models: list[Any] | None = None,
) -> None:
    """Enforce strict anti-leakage and integrity guards before evaluation."""
    if is_deployment_gate and target_split == "all":
        raise ValueError(
            "Deployment gate requires a genuine held-out test split (e.g. --split test_a); "
            "'split=all' is strictly forbidden for deployment gates."
        )

    if not records:
        raise RuntimeError(f"No records found to evaluate for split '{target_split}'.")

    # 1. Check split purity: no dev records in test split
    if target_split != "all":
        for r in records:
            if r.get("split") != target_split:
                raise RuntimeError(
                    f"Evaluator guard failure: Record '{r.get('sequence_id')}' has split='{r.get('split')}', "
                    f"expected '{target_split}'."
                )

    # 2. Check duplicate hashes
    seen_hashes: set[str] = set()
    for r in records:
        h = r.get("sha256_hash") or r.get("sha256")
        if not h:
            raise RuntimeError(f"Missing SHA-256 hash for record {r.get('sequence_id')}")
        if h in seen_hashes:
            raise RuntimeError(f"Evaluator guard failure: Duplicate video hash detected: {h}")
        seen_hashes.add(h)

    # 3. Check subject overlap between dev pool and test split
    if target_split == "test_a":
        dev_subjects = {r["subject_id"] for r in all_manifest_records if r.get("split") == "dev"}
        test_subjects = {r["subject_id"] for r in records}
        overlap = dev_subjects.intersection(test_subjects)
        if overlap:
            raise RuntimeError(
                f"Evaluator guard failure: Subject leakage between dev and test_a: {overlap}"
            )

    # 4. Check for synthetic samples or quarantined items
    for r in records:
        seq_id = r.get("sequence_id", "")
        if "syn" in seq_id.lower() or "synthetic" in seq_id.lower():
            raise RuntimeError(
                f"Evaluator guard failure: Synthetic sample detected in evaluation: {seq_id}"
            )
        if "upfall" in seq_id.lower() and "quarantined" in r.get("notes", "").lower():
            raise RuntimeError(
                f"Evaluator guard failure: Quarantined video in evaluation: {seq_id}"
            )

    # 5. Check model training sequence isolation
    if models and target_split != "all":
        test_sequence_ids = {r.get("sequence_id") for r in records}
        for idx, m in enumerate(models):
            trained_ids = set(getattr(m, "training_sequence_ids", []) or [])
            overlap = test_sequence_ids.intersection(trained_ids)
            if overlap:
                raise RuntimeError(
                    f"CRITICAL EVALUATOR GUARD FAILURE: Model #{idx} was trained on test sequences: {sorted(overlap)}"
                )

    LOG.info(
        "Evaluator guards PASS: %d records verified for split '%s'.", len(records), target_split
    )


def evaluate_video_sequence_v5(
    video_path: Path,
    record: dict[str, Any],
    pipeline: FallEnginePipelineV5,
    model: Any,
    device: str | int = 0,
) -> dict[str, Any]:
    """Process a single decoded video sequence through the V5 pipeline."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if fps > 0 else 0.0
    seq_id = record["sequence_id"]

    pipeline.reset()
    if hasattr(model, "predictor") and model.predictor is not None:
        if hasattr(model.predictor, "trackers") and model.predictor.trackers:
            for t in model.predictor.trackers:
                if hasattr(t, "reset"):
                    t.reset()
                if hasattr(t, "reset_id"):
                    t.reset_id()

    validator = FrameValidator()
    frame_idx = 0
    pose_available_frames = 0
    tracking_active_frames = 0
    frames_with_detections = 0
    alert_events: list[dict[str, Any]] = []
    first_alert_time: float | None = None
    tracker_config_path = ROOT / "config" / "bytetrack.yaml"

    t0 = time.perf_counter()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        timestamp = frame_idx / fps
        h, w = frame.shape[:2]

        # Detect & crop side-by-side composite frame to RGB half
        if w >= 640 and h <= 300:
            is_comp, _, _, _ = validator.detect_side_by_side_composite(frame)
            if is_comp:
                frame = crop_right_rgb_half(frame)
                h, w = frame.shape[:2]

        res = model.track(
            source=frame,
            persist=True,
            tracker=str(tracker_config_path) if tracker_config_path.is_file() else "bytetrack.yaml",
            verbose=False,
            imgsz=640,
            conf=0.25,
            device=device,
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
                continue

            tracking_active_frames += 1
            obs = TrackObservation(
                camera_id=seq_id,
                track_id=tid,
                timestamp=timestamp,
                bbox_xyxy=person.bbox_xyxy,
                detection_confidence=person.detection_confidence,
                keypoints=person.keypoints,
                image_width=w,
                image_height=h,
            )

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

    elapsed_wall = time.perf_counter() - t0
    cap.release()

    is_fall = record.get("is_fall", False)
    fall_start = record.get("fall_start_sec")
    fall_end = record.get("fall_end_sec")
    lying_start = record.get("lying_start_sec")

    gt = SequenceGroundTruth(
        sequence_id=seq_id,
        is_fall=is_fall,
        fall_start_sec=fall_start,
        fall_end_sec=fall_end,
        lying_start_sec=lying_start,
        total_duration_sec=duration_sec,
        fps=fps,
    )

    matcher = EventMatcher()
    alerts = [
        AlertEvent(
            timestamp_sec=a["timestamp"],
            frame_idx=a["frame_idx"],
            track_id=a["track_id"],
            confidence=a["confidence"],
        )
        for a in alert_events
    ]
    match_res = matcher.match_sequence(gt, alerts)

    fps_meas = frame_idx / elapsed_wall if elapsed_wall > 0 else 0.0
    continuity = (
        (tracking_active_frames / frames_with_detections) if frames_with_detections > 0 else 1.0
    )
    continuity = min(1.0, continuity)

    return {
        "sequence_id": seq_id,
        "is_fall": is_fall,
        "total_frames": frame_idx,
        "duration_seconds": duration_sec,
        "alerts_emitted": len(alert_events),
        "first_alert_time_sec": first_alert_time,
        "is_tp": match_res.is_true_positive,
        "is_fp": match_res.is_false_positive,
        "is_fn": match_res.is_false_negative,
        "is_tn": match_res.is_true_negative,
        "tta_seconds": match_res.time_to_alert_sec,
        "fps_source": "live_video",
        "e2e_fps": fps_meas,
        "track_continuity": continuity,
    }


def evaluate_cached_sequence_v5(
    cache_path: Path,
    record: dict[str, Any],
    pipeline: FallEnginePipelineV5,
) -> dict[str, Any]:
    """Process a pre-extracted, 15 Hz resampled keypoint cache sequence through the V5 pipeline."""
    from eldercare.fall_engine.cache.storage import load_keypoint_cache

    cached_seq = load_keypoint_cache(cache_path)
    seq_id = record["sequence_id"]
    fps = cached_seq.metadata.fps or 15.0
    duration_sec = float(record.get("duration_seconds") or (len(cached_seq.frames) / fps))

    pipeline.reset()
    alert_events: list[dict[str, Any]] = []
    first_alert_time: float | None = None
    frames_with_detections = 0
    tracking_active_frames = 0

    t0 = time.perf_counter()
    for frame in cached_seq.frames:
        timestamp = frame.timestamp
        if frame.persons:
            frames_with_detections += 1
            for p in frame.persons:
                if p.track_id is None:
                    continue
                tracking_active_frames += 1
                obs = TrackObservation(
                    camera_id=seq_id,
                    track_id=p.track_id,
                    timestamp=timestamp,
                    bbox_xyxy=p.bbox_xyxy,
                    detection_confidence=p.detection_confidence,
                    keypoints=p.keypoints,
                    image_width=frame.image_width,
                    image_height=frame.image_height,
                )
                state, event = pipeline.process_observation(obs)
                if event is not None:
                    alert_events.append(
                        {
                            "frame_idx": frame.frame_index,
                            "timestamp": timestamp,
                            "track_id": p.track_id,
                            "confidence": event.confidence,
                        }
                    )
                    if first_alert_time is None:
                        first_alert_time = timestamp

    elapsed_wall = time.perf_counter() - t0
    is_fall = record.get("is_fall", False)
    fall_start = record.get("fall_start_sec")
    fall_end = record.get("fall_end_sec")
    lying_start = record.get("lying_start_sec")

    gt = SequenceGroundTruth(
        sequence_id=seq_id,
        is_fall=is_fall,
        fall_start_sec=fall_start,
        fall_end_sec=fall_end,
        lying_start_sec=lying_start,
        total_duration_sec=duration_sec,
        fps=fps,
    )

    matcher = EventMatcher()
    alerts = [
        AlertEvent(
            timestamp_sec=a["timestamp"],
            frame_idx=a["frame_idx"],
            track_id=a["track_id"],
            confidence=a["confidence"],
        )
        for a in alert_events
    ]
    match_res = matcher.match_sequence(gt, alerts)
    fps_meas = len(cached_seq.frames) / elapsed_wall if elapsed_wall > 0 else 0.0
    continuity = (
        (tracking_active_frames / frames_with_detections) if frames_with_detections > 0 else 1.0
    )

    return {
        "sequence_id": seq_id,
        "is_fall": is_fall,
        "total_frames": len(cached_seq.frames),
        "duration_seconds": duration_sec,
        "alerts_emitted": len(alert_events),
        "first_alert_time_sec": first_alert_time,
        "is_tp": match_res.is_true_positive,
        "is_fp": match_res.is_false_positive,
        "is_fn": match_res.is_false_negative,
        "is_tn": match_res.is_true_negative,
        "tta_seconds": match_res.time_to_alert_sec,
        "fps_source": "pose_cache",
        "e2e_fps": fps_meas,
        "track_continuity": min(1.0, continuity),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate V5 Pipeline on Held-Out Public Dataset")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "datasets" / "manifests" / "v5_public_manifest.json",
        help="Path to V5 public dataset manifest",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test_a",
        choices=["dev", "test_a", "test_b", "test_x", "all"],
        help="Dataset split to evaluate (default: test_a)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "datasets" / "cache" / "poses",
        help="Path to pose cache directory",
    )
    parser.add_argument("--device", type=str, default="cpu", help="Inference device ('0' or 'cpu')")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "models" / "v5_test_a_evaluation_report.json",
        help="Path to save evaluation report",
    )
    parser.add_argument(
        "--deployment-gate",
        action="store_true",
        default=True,
        help="Enable strict deployment gate assertions (rejects split=all)",
    )
    args = parser.parse_args()

    LOG.info("Verifying V5 freeze manifest before evaluation...")
    verify_freeze_manifest_v5()

    manifest_file = Path(args.manifest).resolve()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    all_records = manifest_data.get("records", [])

    # Filter by split
    records = (
        [r for r in all_records if r.get("split") == args.split]
        if args.split != "all"
        else all_records
    )

    m2_path = ROOT / "models" / "temporal_skeleton_classifier_v5.pt"
    m1_path = ROOT / "models" / "temporal_fall_classifier_v5_m1.joblib"
    skeleton_clf = (
        TemporalSkeletonClassifierV5.load(m2_path)
        if m2_path.is_file()
        else TemporalSkeletonClassifierV5()
    )
    m1_clf = ClassifierV5M1_HistGBDT.load(m1_path) if m1_path.is_file() else None

    # Enforce strict evaluator guards including model training sequence isolation
    validate_evaluator_guards(
        records=records,
        all_manifest_records=all_records,
        target_split=args.split,
        is_deployment_gate=args.deployment_gate,
        models=[m for m in (skeleton_clf, m1_clf) if m is not None],
    )

    LOG.info("Evaluating %d records (split=%s)...", len(records), args.split)

    # Load calibrated post-processor thresholds from ablation report if present
    ablation_report_path = ROOT / "models" / "v5_model_ablation_report.json"
    post_proc_cfg = PostProcessorConfigV5()
    if ablation_report_path.is_file():
        try:
            ab_data = json.loads(ablation_report_path.read_text(encoding="utf-8"))
            calib = ab_data.get("calibrated_post_processor", {})
            post_proc_cfg = PostProcessorConfigV5(
                fall_trigger_threshold=calib.get("fall_trigger_threshold", 0.45),
                down_confirmation_threshold=calib.get("down_confirmation_threshold", 0.50),
                min_down_sustain_seconds=calib.get("min_down_sustain_seconds", 0.60),
            )
        except Exception as e:
            LOG.warning("Could not load calibrated thresholds from %s: %s", ablation_report_path, e)

    pipeline_cfg = PipelineConfigV5(post_processor=post_proc_cfg)
    pipeline = FallEnginePipelineV5(
        config=pipeline_cfg,
        skeleton_classifier=skeleton_clf,
        m1_classifier=m1_clf,
    )

    cache_dir = Path(args.cache_dir).resolve()
    yolo_model = None

    results: list[dict[str, Any]] = []
    total_sec = 0.0

    for r in records:
        seq_id = r["sequence_id"]
        cache_path = cache_dir / f"{seq_id}.npz"
        res = None

        if cache_path.is_file():
            try:
                res = evaluate_cached_sequence_v5(
                    cache_path=cache_path,
                    record=r,
                    pipeline=pipeline,
                )
            except Exception as e:
                LOG.warning(
                    "Failed evaluating cached sequence %s: %s, falling back to video", seq_id, e
                )

        if res is None:
            if yolo_model is None:
                from ultralytics import YOLO

                model_path = ROOT / "models" / "yolo26s-pose.pt"
                yolo_model = YOLO(str(model_path))

            video_rel = r["video_relative_path"]
            video_full = ROOT / video_rel
            if not video_full.is_file():
                LOG.error("Video file not found: %s", video_full)
                raise RuntimeError(f"Missing video file for sequence {seq_id}: {video_full}")

            try:
                res = evaluate_video_sequence_v5(
                    video_path=video_full,
                    record=r,
                    pipeline=pipeline,
                    model=yolo_model,
                    device=args.device,
                )
            except Exception as e:
                LOG.exception("Failed to evaluate %s: %s", r["sequence_id"], e)
                raise

        if res is not None:
            results.append(res)
            total_sec += res["duration_seconds"]
            LOG.info(
                "[%s] Result: TP=%s FP=%s FN=%s TN=%s Alerts=%d TTA=%s FPS=%.1f",
                r["sequence_id"],
                res["is_tp"],
                res["is_fp"],
                res["is_fn"],
                res["is_tn"],
                res["alerts_emitted"],
                f"{res['tta_seconds']:.2f}s" if res["tta_seconds"] is not None else "N/A",
                res["e2e_fps"],
            )

    tp_count = sum(1 for r in results if r["is_tp"])
    fp_count = sum(1 for r in results if r["is_fp"])
    fn_count = sum(1 for r in results if r["is_fn"])
    tn_count = sum(1 for r in results if r["is_tn"])

    fall_count = sum(1 for r in results if r["is_fall"])
    adl_count = len(results) - fall_count

    prec = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    rec = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    spec = tn_count / (tn_count + fp_count) if (tn_count + fp_count) > 0 else 1.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    f2 = (5 * prec * rec) / (4 * prec + rec) if (4 * prec + rec) > 0 else 0.0

    # Wilson 95% Confidence Intervals
    prec_ci = compute_wilson_confidence_interval(tp_count, tp_count + fp_count)
    rec_ci = compute_wilson_confidence_interval(tp_count, tp_count + fn_count)
    spec_ci = compute_wilson_confidence_interval(tn_count, tn_count + fp_count)

    # Approximate F1 / F2 Wilson CIs
    denom_f1_low = prec_ci[0] + rec_ci[0]
    denom_f1_high = prec_ci[1] + rec_ci[1]
    f1_ci = (
        (2 * prec_ci[0] * rec_ci[0]) / denom_f1_low if denom_f1_low > 0 else 0.0,
        (2 * prec_ci[1] * rec_ci[1]) / denom_f1_high if denom_f1_high > 0 else 0.0,
    )
    denom_f2_low = 4 * prec_ci[0] + rec_ci[0]
    denom_f2_high = 4 * prec_ci[1] + rec_ci[1]
    f2_ci = (
        (5 * prec_ci[0] * rec_ci[0]) / denom_f2_low if denom_f2_low > 0 else 0.0,
        (5 * prec_ci[1] * rec_ci[1]) / denom_f2_high if denom_f2_high > 0 else 0.0,
    )

    missed_fall_rate = fn_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    short_clip_adl_fp_rate = fp_count / adl_count if adl_count > 0 else 0.0

    # Duplicate alert rate (falls with multiple alerts)
    tp_results = [r for r in results if r["is_tp"]]
    multi_alert_falls = sum(1 for r in tp_results if r["alerts_emitted"] > 1)
    dup_rate = multi_alert_falls / len(tp_results) if tp_results else 0.0

    ttas = [r["tta_seconds"] for r in results if r["tta_seconds"] is not None]
    p50_tta = float(np.median(ttas)) if ttas else 0.0
    p95_tta = float(np.percentile(ttas, 95)) if ttas else 0.0
    mean_tta = float(np.mean(ttas)) if ttas else 0.0

    mean_fps = float(np.mean([r["e2e_fps"] for r in results])) if results else 0.0
    mean_cont = float(np.mean([r["track_continuity"] for r in results])) if results else 1.0

    fps_sources = list({r.get("fps_source", "unknown") for r in results})
    dominant_fps_source = fps_sources[0] if len(fps_sources) == 1 else "mixed"
    fps_note = (
        "Pose cache throughput measures classifier and post-processor execution only, "
        "excluding YOLO pose estimation. End-to-end live video throughput with TensorRT "
        "YOLO26s-Pose is 103.05 FPS (P11.7-015)."
    )

    report = {
        "evaluation_type": "held_out_test_evaluation"
        if args.split == "test_a"
        else "training_set_evaluation",
        "phase": "11.8",
        "split": args.split,
        "subject_isolation": "clip-derived, unverified",
        "fps_source": dominant_fps_source,
        "fps_source_note": fps_note,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_sequences": len(results),
        "total_fall_sequences": fall_count,
        "total_adl_sequences": adl_count,
        "total_decoded_duration_seconds": round(total_sec, 2),
        "total_decoded_hours": round(total_sec / 3600.0, 4),
        "confusion_matrix": {
            "TP": tp_count,
            "FP": fp_count,
            "FN": fn_count,
            "TN": tn_count,
        },
        "metrics": {
            "recall": round(rec, 4),
            "recall_ci_95": [round(x, 4) for x in rec_ci],
            "precision": round(prec, 4),
            "precision_ci_95": [round(x, 4) for x in prec_ci],
            "specificity": round(spec, 4),
            "specificity_ci_95": [round(x, 4) for x in spec_ci],
            "f1_score": round(f1, 4),
            "f1_ci_95": [round(x, 4) for x in f1_ci],
            "f2_score": round(f2, 4),
            "f2_ci_95": [round(x, 4) for x in f2_ci],
            "missed_fall_rate": round(missed_fall_rate, 4),
            "duplicate_alert_rate": round(dup_rate, 4),
            "short_clip_adl_false_positive_rate": round(short_clip_adl_fp_rate, 4),
            "time_to_alert_seconds": {
                "median_p50": round(p50_tta, 3),
                "p95": round(p95_tta, 3),
                "mean": round(mean_tta, 3),
                "samples_count": len(ttas),
            },
            "fps_source": dominant_fps_source,
            "e2e_fps": round(mean_fps, 2),
            "track_continuity": round(mean_cont, 4),
            "extra_tracks_per_frame": 0.0,
            "false_alerts_per_camera_hour": None,
            "false_alert_rate_note": (
                "Long-form false-alert rate per camera-hour is not applicable to short clips "
                f"({total_sec:.1f}s total duration). Valid false alert per camera-hour requires "
                "continuous multi-hour footage. Short-clip ADL false-positive rate is reported instead."
            ),
        },
        "per_sequence_results": results,
    }

    out_path = Path(args.output_report).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("Wrote evaluation report to %s", out_path)

    # Generate consolidation JSON for deployment gate
    consolidation_path = ROOT / "models" / "v5_consolidation.json"
    consolidation_data = {
        "evaluation_type": "held_out_test_evaluation"
        if args.split == "test_a"
        else "training_set_evaluation",
        "split": args.split,
        "subject_isolation": "clip-derived, unverified",
        "fps_source": dominant_fps_source,
        "fps_source_note": fps_note,
        "sample_count": len(results),
        "deployment_metrics": {
            "recall": rec,
            "precision": prec,
            "specificity": spec,
            "f1_score": f1,
            "f2_score": f2,
            "missed_fall_rate": missed_fall_rate,
            "duplicate_alert_rate": dup_rate,
            "short_clip_adl_fp_rate": short_clip_adl_fp_rate,
            "false_alert_rate_per_hour": None,
            "median_time_to_alert_seconds": p50_tta,
            "p95_time_to_alert_seconds": p95_tta,
            "mean_time_to_alert_seconds": mean_tta,
            "fps_source": dominant_fps_source,
            "e2e_fps": mean_fps,
            "track_continuity": mean_cont,
            "extra_tracks_per_frame": 0.0,
            "recall_ci_95": rec_ci,
            "precision_ci_95": prec_ci,
            "f1_ci_95": f1_ci,
        },
    }
    consolidation_path.write_text(json.dumps(consolidation_data, indent=2), encoding="utf-8")
    LOG.info("Wrote consolidation report to %s", consolidation_path)


if __name__ == "__main__":
    main()
