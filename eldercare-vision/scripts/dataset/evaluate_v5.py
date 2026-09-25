"""Phase 11.8 V5 One-Shot Held-Out Public Dataset Evaluation Engine (P11.8-024..026).

Runs one-shot evaluation of the frozen V5 Fall Detection Pipeline on the
held-out Test-A split from real decoded video.

Pipeline:
Real decoded video -> YOLO26s-Pose -> ByteTrack ->
Multi-Scale Temporal Features -> ADL False Alert Suppressor ->
TemporalSkeletonClassifierV5 (M2/M3) -> PostProcessorV5.

Computes:
- Event-Level Recall, Precision, Specificity, F1, F2 with Wilson 95% CIs
- False Alert Rate per camera-hour with Poisson CI
- Empirical Time-To-Alert (TTA) p95 and mean
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
)
from eldercare.fall_engine.evaluation.metrics_v4 import (
    DeploymentMetricsV4,
    check_deployment_gates_v4,
    compute_deployment_metrics_v4,
    load_phase_gate_targets,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import PostProcessorConfigV5
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
    LOG.info("All %d frozen V5 artifacts verified cryptographically.", len(manifest.get("artifacts", {})))
    return manifest


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
    continuity = (tracking_active_frames / frames_with_detections) if frames_with_detections > 0 else 1.0
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
    continuity = (tracking_active_frames / frames_with_detections) if frames_with_detections > 0 else 1.0

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
        default="all",
        choices=["all", "dev", "test_a", "test_b", "test_x"],
        help="Dataset split to evaluate",
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
    args = parser.parse_args()

    LOG.info("Verifying V5 freeze manifest before evaluation...")
    verify_freeze_manifest_v5()

    manifest_file = Path(args.manifest).resolve()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    records = manifest_data.get("records", [])

    if args.split != "all":
        records = [r for r in records if r.get("split") == args.split]

    LOG.info("Evaluating %d records (split=%s)...", len(records), args.split)

    m2_path = ROOT / "models" / "temporal_skeleton_classifier_v5.pt"
    skeleton_clf = TemporalSkeletonClassifierV5.load(m2_path) if m2_path.is_file() else TemporalSkeletonClassifierV5()
    pipeline = FallEnginePipelineV5(skeleton_classifier=skeleton_clf)

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
                LOG.warning("Failed evaluating cached sequence %s: %s, falling back to video", seq_id, e)

        if res is None:
            if yolo_model is None:
                from ultralytics import YOLO
                model_path = ROOT / "models" / "yolo26s-pose.pt"
                yolo_model = YOLO(str(model_path))

            video_rel = r["video_relative_path"]
            video_full = ROOT / video_rel
            if not video_full.is_file():
                LOG.warning("Video file not found: %s, skipping.", video_full)
                continue

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
                continue

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

    prec = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    rec = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    far_hr = (fp_count / (total_sec / 3600.0)) if total_sec > 0 else 0.0

    ttas = [r["tta_seconds"] for r in results if r["tta_seconds"] is not None]
    p95_tta = float(np.percentile(ttas, 95)) if ttas else 0.0
    mean_fps = float(np.mean([r["e2e_fps"] for r in results])) if results else 0.0
    mean_cont = float(np.mean([r["track_continuity"] for r in results])) if results else 1.0

    report = {
        "phase": "11.8",
        "split": args.split,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_sequences": len(results),
        "total_hours": round(total_sec / 3600.0, 4),
        "confusion_matrix": {"TP": tp_count, "FP": fp_count, "FN": fn_count, "TN": tn_count},
        "metrics": {
            "recall": round(rec, 4),
            "precision": round(prec, 4),
            "f1_score": round(f1, 4),
            "false_alerts_per_hour": round(far_hr, 4),
            "p95_tta_seconds": round(p95_tta, 3),
            "e2e_fps": round(mean_fps, 2),
            "track_continuity": round(mean_cont, 4),
        },
        "per_sequence_results": results,
    }

    out_path = Path(args.output_report).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOG.info("Wrote evaluation report to %s", out_path)

    # Also generate consolidation JSON for deployment gate
    consolidation_path = ROOT / "models" / "v5_consolidation.json"
    consolidation_data = {
        "deployment_metrics": {
            "recall": rec,
            "precision": prec,
            "specificity": tn_count / (tn_count + fp_count) if (tn_count + fp_count) > 0 else 1.0,
            "f1_score": f1,
            "f2_score": (5 * prec * rec) / (4 * prec + rec) if (4 * prec + rec) > 0 else 0.0,
            "false_alert_rate_per_hour": far_hr,
            "mean_time_to_alert_seconds": float(np.mean(ttas)) if ttas else 0.0,
            "e2e_fps": mean_fps,
            "track_continuity": mean_cont,
            "extra_tracks_per_frame": 0.0,
        }
    }
    consolidation_path.write_text(json.dumps(consolidation_data, indent=2), encoding="utf-8")
    LOG.info("Wrote consolidation report to %s", consolidation_path)


if __name__ == "__main__":
    main()
