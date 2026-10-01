"""Unit tests for the bounded per-track history store (P3-003).

TDD RED-first suite. CPU-only: hand-built ``TrackObservation`` objects, zero
sleeps. Neither this module nor the history source may import
ultralytics/torch/cv2 at runtime — proven by the ``sys.modules`` test and
the AST import scans below (P3-002 pattern).
"""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path
from typing import Any

import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import TrackObservation

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

CAMERA_ID = "cam-01"
TRACK_ID = 7
TIMESTAMP = 12.5


# --- builders ---------------------------------------------------------------


def _keypoints(offset: float = 0.0) -> tuple[Keypoint, ...]:
    return tuple(
        Keypoint(
            x=offset + float(i * 2),
            y=offset + float(i * 2 + 1),
            confidence=0.1 + 0.01 * i,
            present=True,
        )
        for i in range(KEYPOINT_COUNT)
    )


def _observation(**overrides: Any) -> TrackObservation:
    kwargs: dict[str, Any] = {
        "camera_id": CAMERA_ID,
        "track_id": TRACK_ID,
        "timestamp": TIMESTAMP,
        "bbox_xyxy": (10.0, 20.0, 60.0, 120.0),
        "detection_confidence": 0.77,
        "keypoints": _keypoints(),
        "image_width": 640,
        "image_height": 480,
    }
    kwargs.update(overrides)
    return TrackObservation(**kwargs)


def _history(max_observations: int = 60) -> TrackHistory:
    return TrackHistory(TrackHistoryConfig(max_observations=max_observations))


# --- config -----------------------------------------------------------------


def test_config_default_is_documented_engineering_capacity() -> None:
    config = TrackHistoryConfig()
    assert config.max_observations == 60
    assert "history_seconds" in (TrackHistoryConfig.__doc__ or "")


def test_config_frozen() -> None:
    config = TrackHistoryConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.max_observations = 10  # type: ignore[misc]


def test_config_rejects_bad_max() -> None:
    for bad in (True, False, "60", 60.5, None, (60,)):
        with pytest.raises(TypeError, match="max_observations"):
            TrackHistoryConfig(max_observations=bad)  # type: ignore[arg-type]
    for bad in (0, -1, -100):
        with pytest.raises(ValueError, match="max_observations"):
            TrackHistoryConfig(max_observations=bad)  # type: ignore[arg-type]


# --- append / order ---------------------------------------------------------


def test_first_observation_accepted() -> None:
    history = _history()
    obs = _observation(timestamp=5.0)
    history.append(obs)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (obs,)
    assert len(history) == 1
    assert history.keys() == ((CAMERA_ID, TRACK_ID),)


def test_sequential_append_preserves_order() -> None:
    history = _history()
    observations = [_observation(timestamp=float(step)) for step in (1.0, 2.0, 3.0)]
    for obs in observations:
        history.append(obs)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == tuple(observations)


def test_exact_capacity_boundary_no_eviction() -> None:
    history = _history(max_observations=3)
    observations = [_observation(timestamp=float(step)) for step in (1.0, 2.0, 3.0)]
    for obs in observations:
        history.append(obs)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == tuple(observations)


def test_capacity_plus_one_evicts_oldest_newest_retained() -> None:
    history = _history(max_observations=3)
    observations = [_observation(timestamp=float(step)) for step in (1.0, 2.0, 3.0, 4.0)]
    for obs in observations:
        history.append(obs)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == tuple(observations[1:])


def test_multi_append_eviction_sequence() -> None:
    history = _history(max_observations=2)
    observations = [_observation(timestamp=float(step)) for step in range(1, 6)]
    for obs in observations:
        history.append(obs)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == tuple(observations[3:])


def test_separate_tracks_independent() -> None:
    history = _history(max_observations=2)
    history.append(_observation(track_id=1, timestamp=10.0))
    history.append(_observation(track_id=2, timestamp=1.0))
    history.append(_observation(track_id=1, timestamp=11.0))
    history.append(_observation(track_id=1, timestamp=12.0))
    assert [obs.timestamp for obs in history.snapshot(CAMERA_ID, 1)] == [11.0, 12.0]
    assert [obs.timestamp for obs in history.snapshot(CAMERA_ID, 2)] == [1.0]
    assert set(history.keys()) == {(CAMERA_ID, 1), (CAMERA_ID, 2)}


def test_separate_cameras_independent() -> None:
    history = _history(max_observations=2)
    history.append(_observation(camera_id="cam-A", timestamp=9.0))
    history.append(_observation(camera_id="cam-B", timestamp=1.0))
    history.append(_observation(camera_id="cam-A", timestamp=10.0))
    assert [obs.timestamp for obs in history.snapshot("cam-A", TRACK_ID)] == [9.0, 10.0]
    assert [obs.timestamp for obs in history.snapshot("cam-B", TRACK_ID)] == [1.0]


def test_none_track_id_ignored_others_untouched() -> None:
    history = _history()
    kept = _observation(timestamp=1.0)
    history.append(kept)
    history.append(_observation(track_id=None, timestamp=2.0))
    assert history.keys() == ((CAMERA_ID, TRACK_ID),)
    assert len(history) == 1
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (kept,)


def test_duplicate_timestamps_appended_in_arrival_order() -> None:
    history = _history()
    first = _observation(timestamp=3.0, bbox_xyxy=(0.0, 0.0, 10.0, 10.0))
    second = _observation(timestamp=3.0, bbox_xyxy=(20.0, 20.0, 30.0, 30.0))
    history.append(first)
    history.append(second)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (first, second)


def test_out_of_order_raises_and_store_unchanged() -> None:
    history = _history()
    first = _observation(timestamp=2.0)
    history.append(first)
    with pytest.raises(ValueError, match="2.0.*1.0|1.0.*2.0"):
        history.append(_observation(timestamp=1.0))
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (first,)
    history.append(_observation(timestamp=3.0))
    assert [obs.timestamp for obs in history.snapshot(CAMERA_ID, TRACK_ID)] == [2.0, 3.0]


def test_append_wrong_type_raises() -> None:
    history = _history()
    for bad in (None, "obs", 42, {"camera_id": CAMERA_ID}, [1, 2]):
        with pytest.raises(TypeError, match="TrackObservation"):
            history.append(bad)  # type: ignore[arg-type]
    assert len(history) == 0


# --- read-only access / lifecycle -------------------------------------------


def test_unknown_key_snapshot_empty() -> None:
    assert _history().snapshot("no-such-cam", 99) == ()


def test_remove_existing_true_snapshot_empty_others_intact() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=1.0))
    other = _observation(track_id=2, timestamp=2.0)
    history.append(other)
    assert history.remove(CAMERA_ID, 1) is True
    assert history.snapshot(CAMERA_ID, 1) == ()
    assert history.snapshot(CAMERA_ID, 2) == (other,)
    assert len(history) == 1


def test_remove_unknown_false_store_unchanged() -> None:
    history = _history()
    kept = _observation(timestamp=1.0)
    history.append(kept)
    assert history.remove("no-such-cam", 99) is False
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (kept,)
    assert len(history) == 1


def test_clear_empties_all() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=1.0))
    history.append(_observation(camera_id="cam-B", timestamp=2.0))
    history.clear()
    assert len(history) == 0
    assert history.keys() == ()
    assert history.snapshot(CAMERA_ID, 1) == ()
    assert history.snapshot("cam-B", TRACK_ID) == ()


def test_snapshot_immutable_no_mutation_path() -> None:
    history = _history()
    obs = _observation(timestamp=1.0)
    history.append(obs)
    snap = history.snapshot(CAMERA_ID, TRACK_ID)
    assert isinstance(snap, tuple)
    with pytest.raises(TypeError):
        snap[0] = _observation(timestamp=2.0)  # type: ignore[index]
    assert history.snapshot(CAMERA_ID, TRACK_ID) == (obs,)
    assert history.snapshot(CAMERA_ID, TRACK_ID) == snap
    assert history.snapshot(CAMERA_ID, TRACK_ID) is not snap


def test_determinism_identical_sequences_equal() -> None:
    first, second = _history(), _history()
    for history in (first, second):
        for step in range(4):
            history.append(_observation(timestamp=float(step)))
    assert first.snapshot(CAMERA_ID, TRACK_ID) == second.snapshot(CAMERA_ID, TRACK_ID)
    assert first.keys() == second.keys()


def test_snapshot_remove_key_validation_fail_closed() -> None:
    history = _history()
    history.append(_observation(timestamp=1.0))
    for bad_camera in (None, 123, b"cam-01", ""):
        with pytest.raises((TypeError, ValueError), match="camera_id"):
            history.snapshot(bad_camera, TRACK_ID)  # type: ignore[arg-type]
        with pytest.raises((TypeError, ValueError), match="camera_id"):
            history.remove(bad_camera, TRACK_ID)  # type: ignore[arg-type]
    for bad_track in (None, True, "7", 7.5, -1):
        with pytest.raises((TypeError, ValueError), match="track_id"):
            history.snapshot(CAMERA_ID, bad_track)  # type: ignore[arg-type]
        with pytest.raises((TypeError, ValueError), match="track_id"):
            history.remove(CAMERA_ID, bad_track)  # type: ignore[arg-type]
    assert history.snapshot(CAMERA_ID, TRACK_ID) != ()


def test_len_counts_tracked_keys() -> None:
    history = _history()
    assert len(history) == 0
    history.append(_observation(track_id=1, timestamp=1.0))
    history.append(_observation(track_id=2, timestamp=1.0))
    assert len(history) == 2
    history.remove(CAMERA_ID, 1)
    assert len(history) == 1


def test_repr_scalar_only() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=1.0))
    history.append(_observation(track_id=2, timestamp=2.0))
    rendered = repr(history)
    assert "confidence" not in rendered
    assert "max_observations=60" in rendered


# --- framework-freedom proofs ------------------------------------------------


def test_runtime_free_of_frameworks() -> None:
    before = set(sys.modules)
    history = _history()
    history.append(_observation(timestamp=1.0))
    history.snapshot(CAMERA_ID, TRACK_ID)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"history path loaded forbidden module: {module}"


def test_ast_no_framework_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    history_path = repo_root / "src" / "eldercare" / "vision" / "tracking" / "history.py"
    tree = ast.parse(history_path.read_text(encoding="utf-8"))
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
    assert roots, "scanner found no imports at all (vacuous scan)"
    assert not [root for root in roots if root in _FORBIDDEN_RUNTIME_MODULES]
