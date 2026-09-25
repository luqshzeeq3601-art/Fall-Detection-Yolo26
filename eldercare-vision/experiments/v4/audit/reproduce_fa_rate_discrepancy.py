"""P11.7-001 — Reproduce the P11.6-006 false-alert-rate discrepancy.

Replays the frozen V3 holdout evaluation in memory, using the same generator, config and
model as ``experiments/v3/holdout/run_holdout_evaluation_v3.py``. It shows where the reported
0.301 false alerts / camera-hour comes from and how much long-form footage was actually
processed.

Read-only with respect to all V3 artifacts. Writes only
``experiments/v4/audit/P11.7-001-fa-rate-reproduction.json``.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import logging
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from eldercare.fall_engine.confidence.calculator import (  # noqa: E402
    FallConfidenceBreakdown,
)
from eldercare.fall_engine.features.features_v3 import (  # noqa: E402
    TemporalFeaturesV3,
    extract_temporal_features_v3,
)
from eldercare.fall_engine.learned_classifier.classifier_v3 import (  # noqa: E402
    LogisticClassifierV3,
)
from eldercare.fall_engine.state_machine.states import (  # noqa: E402
    FallEvent,
    FallState,
)
from eldercare.fall_engine.state_machine_v3.config_v3 import (  # noqa: E402
    FallStateMachineConfigV3,
)
from eldercare.fall_engine.state_machine_v3.machine_v3 import (  # noqa: E402
    TrackFallStateMachineV3,
)
from eldercare.vision.tracking.observation import TrackObservation  # noqa: E402

HOLDOUT_RUNNER = ROOT / "experiments" / "v3" / "holdout" / "run_holdout_evaluation_v3.py"
MANIFEST = ROOT / "datasets" / "manifests" / "v3_deployment_holdout_manifest.csv"
MODEL = ROOT / "models" / "temporal_fall_classifier_v3.json"
logger = logging.getLogger("reproduce_fa_rate_discrepancy")
OUTPUT = Path(__file__).resolve().parent / "P11.7-001-fa-rate-reproduction.json"


def _load_holdout_runner() -> Any:
    spec = importlib.util.spec_from_file_location("run_holdout_evaluation_v3", HOLDOUT_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v3_holdout_config() -> FallStateMachineConfigV3:
    # Identical to run_holdout_evaluation_v3.py:202-214 with frozen P11.6 defaults.
    return FallStateMachineConfigV3(
        feature_window_sec=1.0,
        descent_velocity_threshold=0.35,
        peak_descent_velocity_threshold=0.70,
        descent_aspect_ratio_drop=-0.25,
        fallen_aspect_ratio_max=1.10,
        fallen_torso_angle_max_deg=40.0,
        min_down_confirming_frames=3,
        down_confirmation_sec=0.6,
        use_angular_velocity=True,
        angular_velocity_descent_threshold=30.0,
        enable_track_stitching=True,
        recovery_aspect_ratio_min=1.35,
        recovery_torso_angle_min_deg=50.0,
        classifier_trigger_threshold=0.45,
        classifier_confirmation_threshold=0.50,
        classifier_veto_threshold=0.0,
    )


def _predict_p11_6_unfixed(clf: LogisticClassifierV3, raw_vec: Sequence[float]) -> float:
    """Reproduce Defect W1: zip silently truncated raw_vec[:12] against 24 weights."""
    score = clf.weights.intercept
    for x, m, s, w in zip(  # noqa: B905
        raw_vec[:12], clf.weights.mean, clf.weights.scale, clf.weights.coefficients
    ):
        norm_x = (x - m) / max(s, 1e-6)
        score += norm_x * w
    clamped = max(-30.0, min(30.0, score))
    return 1.0 / (1.0 + math.exp(-clamped))


class _UnfixedTrackFallStateMachineV3(TrackFallStateMachineV3):
    """Replays the unfixed P11.6 state machine with defects W1, W2, W3 in place."""

    def _is_low_posture(self, feats: TemporalFeaturesV3) -> bool:
        geom = feats.current_geometry
        aspect_low = geom.aspect_ratio <= self.config.fallen_aspect_ratio_max
        angle_low = geom.torso_angle_deg <= self.config.fallen_torso_angle_max_deg
        hip_low = geom.hip_height_ratio >= 0.55
        floor_prox_low = feats.floor_proximity_ratio < 0.2

        if self.config.use_learned_classifier and self.classifier is not None:
            prob = _predict_p11_6_unfixed(self.classifier, feats.feature_vector[:12])
            if prob >= self.config.classifier_confirmation_threshold:
                return True

        return (aspect_low or angle_low) and (hip_low or floor_prox_low)

    def _is_upright_posture(self, feats: TemporalFeaturesV3) -> bool:
        geom = feats.current_geometry
        return bool(
            geom.aspect_ratio >= self.config.recovery_aspect_ratio_min
            and geom.torso_angle_deg >= self.config.recovery_torso_angle_min_deg
        )

    def _is_rapid_descent(self, feats: TemporalFeaturesV3) -> bool:
        peak_vel_trigger = (
            feats.scale_normalized_peak_velocity >= self.config.peak_descent_velocity_threshold
        )
        avg_vel_trigger = (
            feats.scale_normalized_vertical_velocity >= self.config.descent_velocity_threshold
        )
        ratio_drop_trigger = (
            feats.aspect_ratio_relative_change <= self.config.descent_aspect_ratio_drop
            and feats.scale_normalized_vertical_velocity > 0.25
        )
        angular_vel_trigger = False
        if self.config.use_angular_velocity:
            angular_vel_trigger = (
                abs(feats.angular_velocity_deg_per_sec)
                >= self.config.angular_velocity_descent_threshold
                and feats.centroid_acceleration > 0.1
            )
        classifier_trigger = False
        if self.config.use_learned_classifier and self.classifier is not None:
            prob = _predict_p11_6_unfixed(self.classifier, feats.feature_vector[:12])
            classifier_trigger = prob >= self.config.classifier_trigger_threshold

        return (
            peak_vel_trigger
            or avg_vel_trigger
            or ratio_drop_trigger
            or angular_vel_trigger
            or classifier_trigger
        )

    def update(
        self, history: Sequence[TrackObservation]
    ) -> tuple[FallState, FallEvent | None]:
        if not history:
            return self.state, None

        feats = extract_temporal_features_v3(
            history,
            window_seconds=self.config.feature_window_sec,
            gap_threshold=0.1,
        )
        current_time = float(history[-1].timestamp)
        self.last_observation_timestamp = current_time
        emitted_event: FallEvent | None = None

        if self.state == FallState.NORMAL:
            if self._is_rapid_descent(feats):
                self.candidate_timestamp = current_time
                self.candidate_features = feats
                self.down_frame_count = 1 if self._is_low_posture(feats) else 0
                self._transition_to(
                    FallState.DESCENT_CANDIDATE,
                    current_time,
                    f"Rapid descent v3: peak_vel={feats.scale_normalized_peak_velocity:.2f}h/s, "
                    f"angular_vel={feats.angular_velocity_deg_per_sec:.2f}",
                    feats,
                )

        elif self.state == FallState.DESCENT_CANDIDATE:
            cand_time = self.candidate_timestamp or current_time
            if (current_time - cand_time) > self.config.descent_candidate_timeout_sec:
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_frame_count = 0
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Descent candidate timed out without sustaining low posture",
                    feats,
                )
            elif self._is_low_posture(feats):
                self.down_frame_count += 1
                req_frames = self.config.min_down_confirming_frames
                if feats.track_gap_count > 0:
                    req_frames += 2

                if self.down_frame_count >= req_frames:
                    self.down_start_timestamp = current_time
                    self._transition_to(
                        FallState.DOWN_CONFIRMING,
                        current_time,
                        f"Down posture confirmed across {self.down_frame_count} frames",
                        feats,
                    )
            else:
                if self._is_upright_posture(feats):
                    self.candidate_timestamp = None
                    self.candidate_features = None
                    self.down_frame_count = 0
                    self._transition_to(
                        FallState.NORMAL,
                        current_time,
                        "Candidate aborted: upright posture restored",
                        feats,
                    )

        elif self.state == FallState.DOWN_CONFIRMING:
            if self._is_upright_posture(feats):
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_start_timestamp = None
                self.down_frame_count = 0
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Down confirmation aborted: person recovered upright",
                    feats,
                )
            elif self._is_low_posture(feats):
                down_time = self.down_start_timestamp or current_time
                if (current_time - down_time) >= self.config.down_confirmation_sec:
                    dur = current_time - down_time
                    classifier_prob = 0.85
                    if self.config.use_learned_classifier and self.classifier is not None:
                        classifier_prob = _predict_p11_6_unfixed(
                            self.classifier, feats.feature_vector[:12]
                        )

                    confidence_val = min(
                        1.0,
                        max(
                            0.5,
                            0.5 * classifier_prob
                            + 0.3 * (1.0 - min(1.0, feats.current_geometry.aspect_ratio / 1.5))
                            + 0.2 * feats.current_geometry.keypoint_confidence_mean,
                        ),
                    )

                    breakdown = FallConfidenceBreakdown(
                        composite_confidence=round(confidence_val, 4),
                        motion_score=round(
                            min(1.0, feats.scale_normalized_peak_velocity / 1.0), 4
                        ),
                        posture_score=round(
                            max(0.0, 1.0 - feats.current_geometry.aspect_ratio / 1.2), 4
                        ),
                        persistence_score=round(min(1.0, dur / 1.5), 4),
                        missing_keypoint_penalty=0.0,
                        unstable_track_penalty=0.1 if feats.track_gap_count > 0 else 0.0,
                        average_pose_confidence=round(
                            feats.current_geometry.keypoint_confidence_mean, 4
                        ),
                        key_contributing_features={
                            "scale_norm_peak_vel": round(
                                feats.scale_normalized_peak_velocity, 3
                            ),
                            "aspect_ratio": round(feats.current_geometry.aspect_ratio, 3),
                            "torso_angle": round(feats.current_geometry.torso_angle_deg, 1),
                            "classifier_prob": round(classifier_prob, 3),
                        },
                        config_version="3.0.0",
                    )

                    event = FallEvent(
                        camera_id=self.camera_id,
                        track_id=self.track_id,
                        confirmed_timestamp=current_time,
                        candidate_timestamp=self.candidate_timestamp or current_time,
                        down_start_timestamp=down_time,
                        features=None,
                        confidence=breakdown.composite_confidence,
                        reason="Down posture sustained after rapid descent (v3 engine)",
                        confidence_breakdown=breakdown,
                    )
                    self.confirmed_event = event

                    if self.cooldown_manager is not None:
                        if not self.cooldown_manager.is_in_cooldown(
                            self.camera_id, self.track_id, current_time
                        ):
                            self.cooldown_manager.record_incident(
                                self.camera_id, self.track_id, current_time
                            )
                            emitted_event = event
                    else:
                        emitted_event = event

                    self._transition_to(
                        FallState.FALL_CONFIRMED,
                        current_time,
                        f"Fall confirmed v3 (conf={breakdown.composite_confidence:.2f}): "
                        f"sustained low posture for {dur:.2f}s",
                        feats,
                    )

        elif self.state == FallState.FALL_CONFIRMED:
            if self._is_upright_posture(feats):
                self._transition_to(
                    FallState.RECOVERY,
                    current_time,
                    "Recovery started: upright posture detected",
                    feats,
                )

        elif self.state == FallState.RECOVERY:
            if self._is_rapid_descent(feats):
                self.candidate_timestamp = current_time
                self.candidate_features = feats
                self.down_frame_count = 1 if self._is_low_posture(feats) else 0
                self._transition_to(
                    FallState.DESCENT_CANDIDATE,
                    current_time,
                    "Re-fall detected during recovery",
                    feats,
                )
            elif (
                current_time - self.state_entry_timestamp
            ) >= self.config.recovery_cooldown_sec:
                self.candidate_timestamp = None
                self.candidate_features = None
                self.down_start_timestamp = None
                self.down_frame_count = 0
                self.confirmed_event = None
                self._transition_to(
                    FallState.NORMAL,
                    current_time,
                    "Recovery cooldown completed",
                    feats,
                )

        return self.state, emitted_event


def reproduce() -> dict[str, Any]:
    runner = _load_holdout_runner()
    clf = LogisticClassifierV3.load(MODEL)
    config = _v3_holdout_config()
    with open(MANIFEST, encoding="utf-8") as f:
        records = list(csv.DictReader(f))

    false_positives: list[dict[str, Any]] = []
    streams: list[dict[str, Any]] = []
    tp = fn = tn_short = 0
    short_adl_count = 0
    declared_non_fall_hours = 0.0

    for rec in records:
        is_fall = int(rec["is_fall"]) == 1
        dur_hrs = float(rec.get("duration_hours") or 0.0)
        if not is_fall:
            declared_non_fall_hours += dur_hrs or float(rec["duration_seconds"]) / 3600.0

        obs = runner._generate_holdout_observations(rec)
        sm = _UnfixedTrackFallStateMachineV3(
            camera_id=rec["camera_id"], track_id=1, config=config, classifier=clf
        )
        history: list[Any] = []
        event = None
        for o in obs:
            history.append(o)
            _, ev = sm.update(history)
            if ev is not None:
                event = ev
                break

        fps = float(rec["fps"])
        is_stream = dur_hrs > 0 and not is_fall
        if is_stream:
            streams.append(
                {
                    "sample_id": rec["sample_id"],
                    "declared_hours": dur_hrs,
                    "frames_processed": len(obs),
                    "seconds_processed": round(len(obs) / fps, 3),
                    "alert": event is not None,
                }
            )
        elif is_fall:
            tp += event is not None
            fn += event is None
        else:
            short_adl_count += 1
            if event is not None:
                false_positives.append(
                    {
                        "sample_id": rec["sample_id"],
                        "activity": rec["activity"],
                        "lighting": rec["lighting"],
                        "clip_seconds": float(rec["duration_seconds"]),
                        "event_confidence": round(event.confidence, 4),
                    }
                )
            else:
                tn_short += 1

    fp = len(false_positives)
    stream_fp = sum(s["alert"] for s in streams)
    processed_stream_seconds = sum(s["seconds_processed"] for s in streams)
    declared_stream_hours = sum(s["declared_hours"] for s in streams)
    return {
        "task_id": "P11.7-001",
        "purpose": "Resolve P11.6-006 0.301 FA/h vs '0 false alerts in 26.5 h'",
        "inputs": {
            "generator": str(HOLDOUT_RUNNER.relative_to(ROOT)).replace("\\", "/"),
            "manifest": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
            "model": str(MODEL.relative_to(ROOT)).replace("\\", "/"),
        },
        "fall_clips": {"tp": tp, "fn": fn},
        "short_adl_clips": {
            "count": short_adl_count,
            "false_positives": fp,
            "true_negatives": tn_short,
            "false_positive_rate": round(fp / short_adl_count, 4) if short_adl_count else None,
            "false_positive_samples": false_positives,
        },
        "long_form_streams": {
            "count": len(streams),
            "declared_hours": round(declared_stream_hours, 2),
            "seconds_actually_processed": round(processed_stream_seconds, 3),
            "alerts": stream_fp,
            "per_stream": streams,
        },
        "reported_metric_reconstruction": {
            "numerator_false_positive_clips": fp,
            "denominator_declared_non_fall_hours": round(declared_non_fall_hours, 4),
            "reported_false_alerts_per_camera_hour": round(fp / declared_non_fall_hours, 4),
        },
        "conclusion": (
            "The 0.301/h figure divides short-clip false positives by declared long-form hours "
            "(unit mismatch). The long-form streams were rendered as 12 s of synthetic walking "
            "each, so the '0 false alerts in 26.5 camera-hours' claim was never measured. True "
            "long-form false alerts per camera-hour is UNMEASURED."
        ),
    }


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger.setLevel(logging.INFO)
    result = reproduce()
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    rec = result["reported_metric_reconstruction"]
    lf = result["long_form_streams"]
    logger.info(
        "FP clips=%d / declared hours=%.4f -> %.4f/h; long-form processed %.1f s of %.2f h",
        rec["numerator_false_positive_clips"],
        rec["denominator_declared_non_fall_hours"],
        rec["reported_false_alerts_per_camera_hour"],
        lf["seconds_actually_processed"],
        lf["declared_hours"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
