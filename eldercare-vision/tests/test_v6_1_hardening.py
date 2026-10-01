"""Unit Tests for V6.1 Root Cause Fixes & Hardening (Phase 11.8 / V6.1).

Tests:
1. PostProcessor rejects fallen-only posture without kinetic falling descent.
2. PostProcessor suppresses repeat alarms within the same lying episode until upright recovery.
3. Pipeline geometric floor aspect ratio is disabled for partial / missing leg keypoints.
4. Pipeline geometric floor check is disabled for bounding boxes touching the image boundary.
5. SplitGuard allows 'dev_longform' while strictly blocking 'longform_adl_heldout'.
6. 5-Fold CV returns out-of-fold metrics (oof_recall, oof_precision, oof_f1).
"""

from __future__ import annotations

import numpy as np
import pytest

from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
)
from eldercare.fall_engine.learned_classifier.classifier_v5 import (
    PostProcessorConfigV5,
    PostProcessorV5,
)
from eldercare.fall_engine.learned_classifier.skeleton_v5 import (
    TemporalSkeletonClassifierV5,
)
from eldercare.fall_engine.learned_classifier.training_v5 import (
    TrainingSampleV5,
    run_5fold_cross_validation_v5,
)
from eldercare.fall_engine.pipeline_v6_1 import (
    DecisionStageV61,
    FallEnginePipelineV61,
    FrameSignalsV61,
    PipelineConfigV61,
)
from eldercare.vision.pose.adapter import Keypoint
from eldercare.vision.tracking.observation import TrackObservation


def test_postprocessor_rejects_fallen_only_when_require_falling_motion_is_true():
    """Verify that a sequence with high p_fallen but zero p_falling never fires an alert."""
    cfg = PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.30,
        require_falling_motion=True,
    )
    post_proc = PostProcessorV5(config=cfg, camera_id="test_cam", track_id=1)

    alerts = []
    # Feed 30 frames of high p_fallen (0.90) and low p_falling (0.05) - simulating lying down or sitting
    for i in range(30):
        t = i * (1.0 / 15.0)
        emitted = post_proc.update(
            timestamp=t,
            p_falling=0.05,
            p_fallen=0.90,
            is_low_posture=True,
            is_upright=False,
        )
        if emitted:
            alerts.append(t)

    assert (
        len(alerts) == 0
    ), f"Expected 0 alerts for fallen-only sequence, got {len(alerts)}"


def test_postprocessor_accepts_falling_then_fallen_transition():
    """Verify that a legitimate kinetic fall (falling -> fallen) properly fires an alert."""
    cfg = PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.30,
        require_falling_motion=True,
    )
    post_proc = PostProcessorV5(config=cfg, camera_id="test_cam", track_id=1)

    alerts = []
    # 1. Normal state (0.0 to 1.0s)
    for i in range(15):
        t = i * (1.0 / 15.0)
        post_proc.update(
            timestamp=t,
            p_falling=0.05,
            p_fallen=0.05,
            is_low_posture=False,
            is_upright=True,
        )

    # 2. Falling descent (1.0 to 1.5s)
    for i in range(15, 23):
        t = i * (1.0 / 15.0)
        post_proc.update(
            timestamp=t,
            p_falling=0.75,
            p_fallen=0.20,
            is_low_posture=False,
            is_upright=False,
        )

    # 3. Fallen on ground (1.5 to 3.0s)
    for i in range(23, 45):
        t = i * (1.0 / 15.0)
        emitted = post_proc.update(
            timestamp=t,
            p_falling=0.05,
            p_fallen=0.85,
            is_low_posture=True,
            is_upright=False,
        )
        if emitted:
            alerts.append(t)

    assert (
        len(alerts) == 1
    ), f"Expected exactly 1 alert for true fall, got {len(alerts)}"
    # Alert should trigger after sustaining fallen posture for >= min_down_sustain_seconds
    assert alerts[0] >= 1.5 + 0.30 - 0.05


def test_postprocessor_suppress_until_upright_prevents_repeat_alerts():
    """Verify that after an alert, sustained lying down does not repeat alerts even after cooldown expires."""
    cfg = PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.20,
        cooldown_seconds=3.0,
        require_falling_motion=True,
        suppress_until_upright=True,
    )
    post_proc = PostProcessorV5(config=cfg, camera_id="test_cam", track_id=1)

    alerts = []
    # Kinetic fall
    post_proc.update(
        timestamp=1.0,
        p_falling=0.80,
        p_fallen=0.10,
        is_low_posture=False,
        is_upright=False,
    )
    for i in range(15):
        t = 1.1 + i * 0.1
        if post_proc.update(
            timestamp=t,
            p_falling=0.10,
            p_fallen=0.90,
            is_low_posture=True,
            is_upright=False,
        ):
            alerts.append(t)

    assert len(alerts) == 1

    # Now simulate staying on the ground for 10 seconds (well past the 3.0s cooldown)
    for i in range(100):
        t = 3.0 + i * 0.1
        if post_proc.update(
            timestamp=t,
            p_falling=0.80,
            p_fallen=0.90,
            is_low_posture=True,
            is_upright=False,
        ):
            alerts.append(t)

    assert (
        len(alerts) == 1
    ), f"Expected no repeat alerts while still down, got {len(alerts)}"

    # Person stands up upright
    post_proc.update(
        timestamp=14.0,
        p_falling=0.05,
        p_fallen=0.05,
        is_low_posture=False,
        is_upright=True,
    )

    # A second fall occurs later
    post_proc.update(
        timestamp=15.0,
        p_falling=0.85,
        p_fallen=0.10,
        is_low_posture=False,
        is_upright=False,
    )
    for i in range(5):
        t = 15.1 + i * 0.1
        if post_proc.update(
            timestamp=t,
            p_falling=0.10,
            p_fallen=0.90,
            is_low_posture=True,
            is_upright=False,
        ):
            alerts.append(t)

    assert (
        len(alerts) == 2
    ), f"Expected 2nd alert after upright recovery, got {len(alerts)}"


def test_pipeline_geometric_floor_check_requires_leg_keypoints():
    """Verify that cropped or occluded bodies without leg keypoints don't trigger geometric floor aspect ratio."""
    cfg = PipelineConfigV61(
        min_leg_keypoint_confidence=0.35,
        edge_margin_px=10.0,
        bypass_suppressor_on_floor=False,
    )
    pipeline = FallEnginePipelineV61(
        skeleton_classifier=TemporalSkeletonClassifierV5(), config=cfg
    )

    # Create dummy observation with head and shoulders but missing leg keypoints (confs = 0.0)
    keypoints = [
        Keypoint(x=320, y=100, confidence=0.9, present=True),  # 0: nose
        Keypoint(x=325, y=95, confidence=0.9, present=True),  # 1
        Keypoint(x=315, y=95, confidence=0.9, present=True),  # 2
        Keypoint(x=330, y=100, confidence=0.9, present=True),  # 3
        Keypoint(x=310, y=100, confidence=0.9, present=True),  # 4
        Keypoint(x=350, y=150, confidence=0.9, present=True),  # 5: L shoulder
        Keypoint(x=290, y=150, confidence=0.9, present=True),  # 6: R shoulder
        Keypoint(x=360, y=200, confidence=0.8, present=True),  # 7: L elbow
        Keypoint(x=280, y=200, confidence=0.8, present=True),  # 8: R elbow
        Keypoint(x=365, y=240, confidence=0.7, present=True),  # 9: L wrist
        Keypoint(x=275, y=240, confidence=0.7, present=True),  # 10: R wrist
        # Missing / occluded legs:
        Keypoint(x=None, y=None, confidence=0.05, present=False),  # 11: L hip
        Keypoint(x=None, y=None, confidence=0.05, present=False),  # 12: R hip
        Keypoint(x=None, y=None, confidence=0.0, present=False),  # 13: L knee
        Keypoint(x=None, y=None, confidence=0.0, present=False),  # 14: R knee
        Keypoint(x=None, y=None, confidence=0.0, present=False),  # 15: L ankle
        Keypoint(x=None, y=None, confidence=0.0, present=False),  # 16: R ankle
    ]

    # Aspect ratio bbox with h/w = 150 / 200 = 0.75 (would trigger floor check if legs were present)
    obs = TrackObservation(
        camera_id="cam_test",
        track_id=1,
        timestamp=1.0,
        bbox_xyxy=(200, 100, 400, 250),
        detection_confidence=0.85,
        keypoints=keypoints,
        image_width=640,
        image_height=480,
    )

    for i in range(5):
        obs_i = TrackObservation(
            camera_id="cam_test",
            track_id=1,
            timestamp=1.0 + i * 0.1,
            bbox_xyxy=(200, 100, 400, 250),
            detection_confidence=0.85,
            keypoints=keypoints,
            image_width=640,
            image_height=480,
        )
        pipeline.process_observation(obs_i)

    post_proc = pipeline._get_post_processor("cam_test", 1)
    # Floor state should not have set down_start_time since legs are missing
    assert post_proc.down_start_time is None


def test_split_guard_enforces_dev_longform_allowed_and_heldout_blocked():
    """Verify split_guard correctly accepts dev_longform and blocks longform_adl_heldout."""
    # Allowed splits in training
    DatasetSplitGuard.enforce_training_isolation("dev")
    DatasetSplitGuard.enforce_training_isolation("dev_longform")
    DatasetSplitGuard.enforce_training_isolation("train")

    # Strictly forbidden splits in training
    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
        DatasetSplitGuard.enforce_training_isolation("longform_adl_heldout")

    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
        DatasetSplitGuard.enforce_training_isolation("test_b")

    with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
        DatasetSplitGuard.enforce_training_isolation("test_a")


def test_cross_validation_returns_oof_metrics():
    """Verify run_5fold_cross_validation_v5 returns out-of-fold metrics."""
    # Create small synthetic sample list
    dummy_samples = []
    for i in range(50):
        label = 1 if (i % 5 == 0) else 0
        skel = np.random.randn(30, 72).astype(np.float32)
        hand = np.random.randn(24).astype(np.float32)
        dummy_samples.append(
            TrainingSampleV5(
                sample_id=f"seq_{i}",
                source_dataset="synth",
                subject_id=f"subj_{i % 10}",
                label_3class=label,
                is_fall_event=(label == 1),
                skeleton_tensor=skel,
                hand_features_multiscale=hand,
            )
        )

    cv_res = run_5fold_cross_validation_v5(dummy_samples, n_splits=5)
    assert "oof_recall" in cv_res
    assert "oof_precision" in cv_res
    assert "oof_f1" in cv_res
    assert isinstance(cv_res["oof_recall"], float)
    assert isinstance(cv_res["oof_precision"], float)
    assert isinstance(cv_res["oof_f1"], float)


def _sig(t: float, p_falling: float, p_fallen: float, **kw: object) -> FrameSignalsV61:
    return FrameSignalsV61(
        camera_id="cam",
        track_id=1,
        timestamp=t,
        has_history=True,
        p_falling=p_falling,
        p_fallen=p_fallen,
        **kw,  # type: ignore[arg-type]
    )


def test_decision_stage_suppression_keeps_alerted_episode_latch():
    """A suppressor hit while lying after an alert must not re-arm the alert."""
    cfg = PipelineConfigV61()
    cfg.post_processor = PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.2,
        cooldown_seconds=1.0,
        require_falling_motion=True,
        suppress_until_upright=True,
    )
    stage = DecisionStageV61(cfg)
    alerts = 0
    t = 0.0
    for p_f, p_d, supp in [(0.9, 0.1, False)] + [(0.1, 0.9, False)] * 10:
        t += 0.1
        _, ev = stage.step(_sig(t, p_f, p_d, heuristic_suppressed=supp))
        alerts += ev is not None
    assert alerts == 1
    # Suppressor fires mid-episode, then another kinetic-looking spike while still down.
    for p_f, p_d, supp in [(0.9, 0.9, True)] + [(0.9, 0.9, False)] * 40:
        t += 0.1
        _, ev = stage.step(_sig(t, p_f, p_d, heuristic_suppressed=supp))
        alerts += ev is not None
    assert alerts == 1


def test_aggregate_metrics_separate_adl_and_fall_clip_false_alerts():
    """Specificity uses ADL clips only; precision counts every unmatched alert."""
    from eldercare.fall_engine.evaluation.event_matching import (
        AlertEvent,
        EventMatcher,
        SequenceGroundTruth,
        aggregate_event_results,
    )

    m = EventMatcher()
    fall = SequenceGroundTruth(
        "f", is_fall=True, fall_start_sec=2.0, lying_start_sec=3.0
    )
    adl_ok = SequenceGroundTruth("a1", is_fall=False)
    adl_bad = SequenceGroundTruth("a2", is_fall=False)
    results = [
        # TP plus one stray alert long after the window
        m.match_sequence(fall, [AlertEvent(2.5, 0, 1), AlertEvent(20.0, 0, 1)]),
        m.match_sequence(adl_ok, []),
        m.match_sequence(adl_bad, [AlertEvent(1.0, 0, 1), AlertEvent(9.0, 0, 1)]),
    ]
    agg = aggregate_event_results(results)
    assert (agg.tp, agg.fn, agg.tn, agg.fp) == (1, 0, 1, 1)
    assert agg.tn + agg.fp == agg.total_adl_sequences
    assert agg.false_alerts_total == 3
    assert agg.fall_sequences_with_false_alerts == 1
    assert agg.specificity == pytest.approx(0.5)
    assert agg.precision == pytest.approx(1 / 4)


def test_v5_pipeline_matches_frozen_hash():
    """pipeline_v5.py is hash-locked by models/v5_freeze_manifest.json."""
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "models" / "v5_freeze_manifest.json").read_text(encoding="utf-8")
    )
    rel = "src/eldercare/fall_engine/pipeline_v5.py"
    frozen = json.dumps(manifest)
    actual = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    assert actual in frozen


def _pp_cfg() -> PostProcessorConfigV5:
    return PostProcessorConfigV5(
        fall_trigger_threshold=0.45,
        down_confirmation_threshold=0.50,
        min_down_sustain_seconds=0.2,
        require_falling_motion=True,
        suppress_until_upright=True,
    )


def _kinetic_fall_with_suppressor_hits() -> list[FrameSignalsV61]:
    # Kinetic descent where the heuristic suppressor fires on every other frame,
    # followed by a sustained fallen posture.
    sigs = []
    t = 0.0
    for i in range(8):
        t += 0.1
        sigs.append(_sig(t, 0.95, 0.05, heuristic_suppressed=(i % 2 == 0)))
    for i in range(10):
        t += 0.1
        sigs.append(_sig(t, 0.05, 0.9, heuristic_suppressed=(i % 2 == 0)))
    return sigs


def test_fix_a_suppressor_ignored_during_kinetic_peak():
    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    base = PipelineConfigV61(post_processor=_pp_cfg())
    fixed = PipelineConfigV61(
        post_processor=_pp_cfg(), suppress_only_without_kinetic_peak=True
    )
    sigs = _kinetic_fall_with_suppressor_hits()
    assert replay_signals(sigs, base) == []
    assert len(replay_signals(sigs, fixed)) == 1


def test_fix_a_suppressor_still_applies_without_kinetic_peak():
    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    fixed = PipelineConfigV61(
        post_processor=_pp_cfg(),
        suppress_only_without_kinetic_peak=True,
        kinetic_peak_hold_sec=0.5,
    )
    sigs = [_sig(0.1, 0.95, 0.05)]  # brief peak, then a slow controlled descent
    sigs += [
        _sig(1.0 + 0.1 * i, 0.30, 0.9, heuristic_suppressed=True) for i in range(15)
    ]
    assert replay_signals(sigs, fixed) == []


def test_fix_b_bottom_edge_contact_keeps_floor_check():
    from eldercare.fall_engine.pipeline_v6_1 import is_floor_posture

    lying_at_bottom = _sig(
        1.0,
        0.0,
        0.0,
        geometric_floor=True,
        has_full_body=True,
        touches_bottom_edge=True,
    )
    cut_off_side = _sig(
        1.0, 0.0, 0.0, geometric_floor=True, has_full_body=True, touches_other_edge=True
    )
    assert not is_floor_posture(lying_at_bottom, PipelineConfigV61())
    assert is_floor_posture(lying_at_bottom, PipelineConfigV61(edge_check_bottom=False))
    assert not is_floor_posture(
        cut_off_side, PipelineConfigV61(edge_check_bottom=False)
    )


def test_identity_jump_frames_are_dropped():
    from types import SimpleNamespace

    from eldercare.fall_engine.pipeline_v6_1 import observations_from_cached_sequence

    def frame(t: float, bbox: tuple[float, float, float, float]) -> SimpleNamespace:
        person = SimpleNamespace(
            track_id=1,
            bbox_xyxy=bbox,
            detection_confidence=0.9,
            keypoints=tuple(
                Keypoint(x=None, y=None, confidence=0.0, present=False)
                for _ in range(17)
            ),
        )
        return SimpleNamespace(
            timestamp=t, persons=(person,), image_width=640, image_height=480
        )

    near = (100.0, 300.0, 200.0, 480.0)
    far = (400.0, 100.0, 440.0, 180.0)  # different detection across the frame
    seq = SimpleNamespace(
        frames=[frame(0.0, near), frame(0.07, near), frame(0.13, far), frame(0.2, near)]
        + [frame(2.0, far)]  # after the re-lock window a new detection is accepted
    )
    stats: dict[str, int] = {}
    obs = observations_from_cached_sequence(
        seq, "cam", max_center_jump_frac=0.25, stats=stats
    )
    assert [o.timestamp for o in obs] == [0.0, 0.07, 0.2, 2.0]
    assert stats == {"kept": 4, "dropped_identity_jumps": 1}
    assert len(observations_from_cached_sequence(seq, "cam")) == 5


def test_replay_matches_process_observation():
    """Precomputed-signal replay (used by calibration) matches live processing."""
    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    rng = np.random.default_rng(0)
    cfg = PipelineConfigV61(post_processor=_pp_cfg(), edge_check_bottom=False)
    model = TemporalSkeletonClassifierV5()
    live = FallEnginePipelineV61(skeleton_classifier=model, config=cfg)
    precompute = FallEnginePipelineV61(skeleton_classifier=model, config=cfg)

    live_alerts, sigs = [], []
    for i in range(60):
        cy = 200 + 4 * i + rng.normal(0, 3)
        kps = [
            Keypoint(
                x=320 + rng.normal(0, 5), y=cy + 10 * k, confidence=0.9, present=True
            )
            for k in range(17)
        ]
        obs = TrackObservation(
            camera_id="cam",
            track_id=1,
            timestamp=i / 15.0,
            bbox_xyxy=(280, cy - 20, 360, min(cy + 180, 479)),
            detection_confidence=0.9,
            keypoints=kps,
            image_width=640,
            image_height=480,
        )
        _, ev = live.process_observation(obs)
        if ev is not None:
            live_alerts.append(obs.timestamp)
        sigs.append(precompute.compute_signals(obs, keep_features=False))

    assert replay_signals(sigs, cfg) == live_alerts


def test_camera_handover_carries_kinetic_evidence_to_new_track():
    """A fall whose track is re-issued mid-descent must still alert under
    require_falling_motion: the new track inherits the trigger's kinetic peak."""
    from dataclasses import replace

    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    cfg = PipelineConfigV61(post_processor=_pp_cfg())
    assert cfg.post_processor.require_falling_motion
    sigs = [_sig(0.1 * i, 0.9, 0.1) for i in range(1, 4)]  # track 1 falls, then is lost
    sigs += [
        replace(_sig(0.4 + 0.1 * i, 0.1, 0.9), track_id=2) for i in range(1, 15)
    ]  # re-issued as track 2, lying
    assert len(replay_signals(sigs, cfg)) == 1

    # Without any kinetic trigger in the window, a lying-only track still cannot alert.
    lying_only = [replace(_sig(0.1 * i, 0.1, 0.9), track_id=2) for i in range(1, 15)]
    assert replay_signals(lying_only, cfg) == []


def test_descent_low_posture_confirms_foreshortened_fall():
    """With descent_low_posture, a kinetic trigger followed by a large body-normalised
    hip drop confirms the fall even when p_fallen stays low; it is off by default."""
    from dataclasses import replace

    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    sigs = [_sig(0.1 * i, 0.9, 0.1) for i in range(1, 4)]
    sigs += [
        replace(_sig(0.3 + 0.1 * i, 0.1, 0.2), descent_ratio=1.4, flatness_ratio=0.2)
        for i in range(1, 12)
    ]
    off = PipelineConfigV61(post_processor=_pp_cfg())
    on = PipelineConfigV61(post_processor=_pp_cfg(), descent_low_posture=True)
    assert replay_signals(sigs, off) == []
    assert len(replay_signals(sigs, on)) == 1

    # Upright-looking body (head well above hips) does not count even after a drop.
    upright = [replace(s, flatness_ratio=1.5) for s in sigs]
    assert replay_signals(upright, on) == []


def test_descent_ratios_measure_drop_against_standing_torso():
    from eldercare.fall_engine.pipeline_v6_1 import descent_ratios

    def obs(t: float, hip_y: float, head_y: float) -> TrackObservation:
        kps = [Keypoint(x=None, y=None, confidence=0.0, present=False)] * 17
        kps[0] = Keypoint(x=100.0, y=head_y, confidence=0.9, present=True)
        shoulder_y = hip_y - 100.0 if head_y < hip_y - 50 else hip_y
        kps[5] = Keypoint(x=90.0, y=shoulder_y, confidence=0.9, present=True)
        kps[11] = Keypoint(x=100.0, y=hip_y, confidence=0.9, present=True)
        return TrackObservation(
            camera_id="c",
            track_id=1,
            timestamp=t,
            bbox_xyxy=(50.0, min(head_y, hip_y) - 10, 150.0, hip_y + 100),
            detection_confidence=0.9,
            keypoints=tuple(kps),
            image_width=640,
            image_height=480,
        )

    hist = [obs(0.1 * i, 200.0, 60.0) for i in range(10)]  # standing, torso ~100 px
    hist += [obs(1.0 + 0.1 * i, 330.0, 320.0) for i in range(5)]  # hips dropped 130 px, flat
    descent, flat = descent_ratios(hist)
    assert descent > 1.0
    assert flat < 0.5


def test_no_kinetic_trigger_means_no_alert_so_calibration_may_skip_replay():
    """Below the trigger threshold nothing alerts, even with sustained low posture."""
    from dataclasses import replace

    from eldercare.fall_engine.pipeline_v6_1 import replay_signals

    cfg = PipelineConfigV61(post_processor=_pp_cfg(), descent_low_posture=True)
    sigs = [
        _sig(0.1 * i, 0.44, 0.95, geometric_floor=True, has_full_body=True,
             descent_ratio=2.0, flatness_ratio=0.0)
        for i in range(60)
    ]
    sigs += [replace(s, track_id=2, timestamp=s.timestamp + 6.0) for s in sigs]
    assert max(s.p_falling for s in sigs) < cfg.post_processor.fall_trigger_threshold
    assert replay_signals(sigs, cfg) == []


def test_calibration_fa_rate_summary_uses_exact_poisson_interval():
    """Zero alerts in 64 h gives an upper 95% bound of ~3.69/64 per hour."""
    from scripts.dataset.calibrate_event_v6_1 import fa_rate_summary

    s = fa_rate_summary(0, 64 * 3600.0)
    assert s["fa_per_hour"] == 0.0
    assert s["fa_per_hour_ci95"][0] == 0.0
    assert abs(s["fa_per_hour_ci95"][1] - 3.6889 / 64) < 1e-3
    lo, hi = fa_rate_summary(3, 4.3 * 3600.0)["fa_per_hour_ci95"]
    assert lo < 3 / 4.3 < hi
