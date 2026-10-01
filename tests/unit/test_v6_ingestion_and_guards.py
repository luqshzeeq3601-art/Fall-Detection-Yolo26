"""Unit tests for Stage 1 / V6 Dataset Ingestion and Evaluator Guards.

Verifies:
1. UP-Fall file name parser patterns and activity mapping.
2. Partition allocation (Dev vs Test-A vs Test-X vs Test-B reserve).
3. Authenticity validator rejecting flat synthetic frames.
4. Master manifest builder asserting zero subject overlap and zero hash collisions.
5. Evaluator guard assertions on V6 splits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dataset.ingest_v6 import (
    IngestionRecordV6,
    build_v6_manifest,
    longform_subject_and_split,
    parse_upfall_filename,
)

ROOT = Path(__file__).resolve().parents[2]


def test_upfall_filename_parser_canonical():
    """Verify parsing of canonical UP-Fall file naming format."""
    meta = parse_upfall_filename("Subject12Activity1Trial2Camera1.mp4")
    assert meta is not None
    assert meta["subject_id"] == "upfall_subj_12"
    assert meta["subject_num"] == 12
    assert meta["activity_num"] == 1
    assert meta["activity_label"] == "fall_forward_hands"
    assert meta["is_fall"] is True
    assert meta["trial_num"] == 2
    assert meta["camera_id"] == "cam1"
    assert meta["split"] == "test_a"


def test_upfall_filename_parser_dev_split():
    """Verify subjects 1..11 are correctly routed to Dev partition."""
    meta = parse_upfall_filename("Subject5Activity6Trial1Camera2.mp4")
    assert meta is not None
    assert meta["subject_id"] == "upfall_subj_05"
    assert meta["activity_label"] == "walking"
    assert meta["is_fall"] is False
    assert meta["split"] == "dev"


def test_upfall_filename_parser_test_x_viewpoint():
    """Verify Camera 2 for held-out subjects 12..17 is routed to Test-X."""
    meta = parse_upfall_filename("Subject14Activity3Trial1Camera2.mp4")
    assert meta is not None
    assert meta["subject_id"] == "upfall_subj_14"
    assert meta["is_fall"] is True
    assert meta["camera_id"] == "cam2"
    assert meta["split"] == "test_x"


def test_upfall_filename_parser_test_b_reserve():
    """Verify Trial 3 for held-out subjects 12..17 is held back in reserve (Test-B)."""
    meta = parse_upfall_filename("Subject15Activity2Trial3Camera1.mp4")
    assert meta is not None
    assert meta["subject_id"] == "upfall_subj_15"
    assert meta["trial_num"] == 3
    assert meta["split"] == "test_b"


def test_upfall_all_activities_classification():
    """Verify all 11 UP-Fall activities are mapped correctly to Fall vs ADL."""
    falls = [1, 2, 3, 4, 5]
    adls = [6, 7, 8, 9, 10, 11]

    for a in falls:
        meta = parse_upfall_filename(f"Subject1Activity{a}Trial1Camera1.mp4")
        assert meta is not None
        assert meta["is_fall"] is True, f"Activity {a} should be a Fall"

    for a in adls:
        meta = parse_upfall_filename(f"Subject1Activity{a}Trial1Camera1.mp4")
        assert meta is not None
        assert meta["is_fall"] is False, f"Activity {a} should be an ADL"


def test_manifest_builder_zero_subject_leakage(tmp_path: Path):
    """Verify that build_v6_manifest raises RuntimeError if subject overlap is detected."""
    rec_dev = IngestionRecordV6(
        source_dataset="UP-Fall",
        sequence_id="seq_01",
        subject_id="subj_01",
        camera_id="cam1",
        environment="lab",
        fps=30.0,
        duration_seconds=5.0,
        total_frames=150,
        resolution_w=640,
        resolution_h=480,
        is_fall=True,
        activity_label="fall",
        fall_start_sec=1.0,
        fall_end_sec=2.5,
        lying_start_sec=3.0,
        license_type="CC-BY-4.0",
        split="dev",
        video_relative_path="path/to/dev.mp4",
        sha256_hash="hash_dev_01",
    )
    # Leaked record: same subject_id in test_a
    rec_leaked = IngestionRecordV6(
        source_dataset="UP-Fall",
        sequence_id="seq_02",
        subject_id="subj_01",  # LEAKAGE
        camera_id="cam1",
        environment="lab",
        fps=30.0,
        duration_seconds=5.0,
        total_frames=150,
        resolution_w=640,
        resolution_h=480,
        is_fall=True,
        activity_label="fall",
        fall_start_sec=1.0,
        fall_end_sec=2.5,
        lying_start_sec=3.0,
        license_type="CC-BY-4.0",
        split="test_a",
        video_relative_path="path/to/test.mp4",
        sha256_hash="hash_test_02",
    )

    out_json = tmp_path / "test_manifest.json"
    with pytest.raises(RuntimeError, match="Subject leakage detected between Dev and Test-A"):
        build_v6_manifest([rec_dev, rec_leaked], out_json, enforce_counts=False)


def test_manifest_builder_duplicate_hash_rejection(tmp_path: Path):
    """Verify that build_v6_manifest raises RuntimeError if duplicate file hashes exist."""
    rec1 = IngestionRecordV6(
        source_dataset="UP-Fall",
        sequence_id="seq_01",
        subject_id="subj_01",
        camera_id="cam1",
        environment="lab",
        fps=30.0,
        duration_seconds=5.0,
        total_frames=150,
        resolution_w=640,
        resolution_h=480,
        is_fall=True,
        activity_label="fall",
        fall_start_sec=1.0,
        fall_end_sec=2.5,
        lying_start_sec=3.0,
        license_type="CC-BY-4.0",
        split="dev",
        video_relative_path="path/to/dev1.mp4",
        sha256_hash="duplicate_hash",
    )
    rec2 = IngestionRecordV6(
        source_dataset="UP-Fall",
        sequence_id="seq_02",
        subject_id="subj_02",
        camera_id="cam1",
        environment="lab",
        fps=30.0,
        duration_seconds=5.0,
        total_frames=150,
        resolution_w=640,
        resolution_h=480,
        is_fall=False,
        activity_label="walking",
        fall_start_sec=None,
        fall_end_sec=None,
        lying_start_sec=None,
        license_type="CC-BY-4.0",
        split="dev",
        video_relative_path="path/to/dev2.mp4",
        sha256_hash="duplicate_hash",  # DUPLICATE
    )

    out_json = tmp_path / "test_manifest.json"
    with pytest.raises(RuntimeError, match="Duplicate video SHA-256 hashes detected"):
        build_v6_manifest([rec1, rec2], out_json, enforce_counts=False)


def test_dataset_split_guard_training_isolation():
    """Verify that DatasetSplitGuard prevents training code from touching test splits."""
    from eldercare.fall_engine.evaluation.split_guard import (
        DatasetSplitGuard,
        HoldoutAccessError,
    )

    # Allowed in training
    DatasetSplitGuard.enforce_training_isolation("dev")
    DatasetSplitGuard.enforce_training_isolation("train")

    # Prohibited in training
    for forbidden in ["test_a", "test_x", "test_b", "holdout", "test"]:
        with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
            DatasetSplitGuard.enforce_training_isolation(forbidden)


def test_split_roles_mark_test_a_x_burned_and_final_splits_sealed():
    """Test-A/Test-X are burned diagnostics; only Test-B and longform held-out are final."""
    from eldercare.fall_engine.evaluation.split_guard import (
        BURNED_SPLITS,
        SEALED_SPLITS,
        DatasetSplitGuard,
        HoldoutAccessError,
        split_role,
    )

    assert {"test_a", "test_x"} == set(BURNED_SPLITS)
    assert {"test_b", "longform_adl_heldout"} <= SEALED_SPLITS
    assert split_role("dev_longform") == "development"

    DatasetSplitGuard.enforce_sealed_access(["test_a", "test_x", "dev"], allow_sealed=False)
    for sealed in ["test_b", "longform_adl_heldout"]:
        with pytest.raises(HoldoutAccessError, match="ILLEGAL ACCESS"):
            DatasetSplitGuard.enforce_sealed_access([sealed], allow_sealed=False)
    DatasetSplitGuard.enforce_sealed_access(["test_b"], allow_sealed=True)


def test_longform_chunks_group_by_creator_and_hold_out_creators():
    """Chunks of one creator share a subject id; held-out creators leave dev_longform."""
    a = longform_subject_and_split("HotCooking_netbhEdnrx8_00h00m-00h26m")
    b = longform_subject_and_split("HotCooking_T6LNhbn7y4M_01h18m-01h44m")
    assert a == b == ("longform_hotcooking", "dev_longform")
    assert longform_subject_and_split("LaurenWhittington_WKcUIpisV_o_00m00-25m00") == (
        "longform_laurenwhittington",
        "longform_adl_heldout",
    )


def test_summarize_by_group_splits_metrics_per_camera():
    """Per-camera summary separates recall by camera key."""
    from eldercare.fall_engine.evaluation.event_matching import (
        EventMatchResult,
        summarize_by_group,
    )

    results = [
        EventMatchResult("a", True, is_true_positive=True, time_to_alert_sec=1.0),
        EventMatchResult("b", True, is_false_negative=True),
        EventMatchResult("c", True, is_false_negative=True),
        EventMatchResult("d", False, is_true_negative=True),
    ]
    summary = summarize_by_group(results, ["cam1", "cam2", "cam2", "cam2"])
    assert summary["cam1"]["recall"] == 1.0
    assert summary["cam2"]["recall"] == 0.0
    assert summary["cam2"]["tn"] == 1
    with pytest.raises(ValueError):
        summarize_by_group(results, ["cam1"])


def test_charades_fall_mentions_ignore_falling_asleep():
    """Fall/trip/slip/collapse words flag a clip; 'falls asleep' does not."""
    from scripts.dataset.ingest_v6 import charades_fall_mentions

    assert charades_fall_mentions("A person trips over a towel.", None) == ["trips"]
    assert charades_fall_mentions("Person sits on the sofa and falls asleep.") == []
    assert charades_fall_mentions("They fell asleep, then slipped on the floor") == ["slipped"]
    assert charades_fall_mentions("A person opens a laptop (waterfall screensaver)") == []


def test_charades_subject_split_is_deterministic_and_hour_weighted():
    """Held-out subjects are hash-ordered and cover ~the requested fraction of hours."""
    from scripts.dataset.ingest_v6 import split_charades_subjects

    seconds = {f"S{i:03d}": 600.0 + 10.0 * i for i in range(100)}
    heldout = split_charades_subjects(seconds, 0.2)
    assert heldout == split_charades_subjects(dict(reversed(seconds.items())), 0.2)
    frac = sum(seconds[s] for s in heldout) / sum(seconds.values())
    assert 0.2 <= frac < 0.2 + max(seconds.values()) / sum(seconds.values())
    assert heldout != split_charades_subjects(seconds, 0.2, salt="other")


def test_zip_member_reference_round_trip(tmp_path: Path):
    """'<zip>::<member>' references parse back to the archive and member."""
    from scripts.dataset.extract_pose_cache import split_zip_member_path

    ref = Path(f"{tmp_path.as_posix()}/videos.zip::Charades_v1_480/ABC12.mp4")
    zip_path, member = split_zip_member_path(ref)
    assert zip_path == tmp_path / "videos.zip"
    assert member == "Charades_v1_480/ABC12.mp4"
    assert split_zip_member_path(tmp_path / "plain.mp4") is None


def test_manifest_counts_charades_per_split(tmp_path: Path):
    """Charades records are reported per split; dev/held-out subjects must not overlap."""

    def rec(seq: str, subj: str, split: str) -> IngestionRecordV6:
        return IngestionRecordV6(
            source_dataset="Charades",
            sequence_id=seq,
            subject_id=subj,
            camera_id="cam0",
            environment="home_kitchen",
            fps=30.0,
            duration_seconds=1800.0,
            total_frames=54000,
            resolution_w=640,
            resolution_h=480,
            is_fall=False,
            activity_label="charades_scripted_adl",
            fall_start_sec=None,
            fall_end_sec=None,
            lying_start_sec=None,
            license_type="Charades-NonCommercial",
            split=split,
            video_relative_path=f"x.zip::{seq}.mp4",
            sha256_hash=seq,
            is_long_form=True,
        )

    m = build_v6_manifest(
        [rec("a", "charades_s1", "dev_longform"), rec("b", "charades_s2", "longform_adl_heldout")],
        out_json=tmp_path / "m.json",
        enforce_counts=False,
    )
    info = m["partition_verification"]["charades"]
    assert info["dev_longform"] == {"count": 1, "hours": 0.5, "subjects": 1}
    assert info["longform_adl_heldout"]["count"] == 1
    assert m["manifest_version"] == "6.5.0"
    with pytest.raises(RuntimeError, match="dev_longform and longform_adl_heldout"):
        build_v6_manifest(
            [
                rec("a", "charades_s1", "dev_longform"),
                rec("b", "charades_s1", "longform_adl_heldout"),
            ],
            out_json=tmp_path / "m2.json",
            enforce_counts=False,
        )
