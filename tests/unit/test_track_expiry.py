"""Unit tests for stale-track expiry on the bounded history store (P3-004).

TDD RED-first suite for ``TrackHistory.expire_stale``. CPU-only:
hand-built ``TrackObservation`` objects, zero sleeps, caller-provided
``now`` (no clocks). Neither this module nor the history source may
import ultralytics/torch/cv2 at runtime — proven by the ``sys.modules``
test and the AST import scans below (P3-002/P3-003 pattern).

Scope: the NEW expiry contract only (latest-timestamp basis, strict
``>`` boundary, insertion-order tuple, idempotency, reuse, fail-closed
validation, bulk reclamation). Append/ordering/eviction/snapshot
internals already pinned by ``test_track_history.py`` are NOT
re-asserted here.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

from eldercare.vision.pose.adapter import KEYPOINT_COUNT, Keypoint
from eldercare.vision.tracking.history import TrackHistory, TrackHistoryConfig
from eldercare.vision.tracking.observation import TrackObservation

_FORBIDDEN_RUNTIME_MODULES = ("torch", "ultralytics", "cv2")

CAMERA_A = "cam-a"
CAMERA_B = "cam-b"


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


def _observation(
    camera_id: str = CAMERA_A, track_id: int | None = 1, timestamp: float = 10.0
) -> TrackObservation:
    return TrackObservation(
        camera_id=camera_id,
        track_id=track_id,
        timestamp=timestamp,
        bbox_xyxy=(10.0, 20.0, 60.0, 120.0),
        detection_confidence=0.77,
        keypoints=_keypoints(),
        image_width=640,
        image_height=480,
    )


def _history(max_observations: int = 60) -> TrackHistory:
    return TrackHistory(TrackHistoryConfig(max_observations=max_observations))


# --- active / stale ---------------------------------------------------------


def test_active_track_survives() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    expired = history.expire_stale(12.0, max_idle_seconds=5.0)
    assert expired == ()
    assert history.keys() == ((CAMERA_A, 1),)


def test_stale_track_expires_exact_key() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_A, 1),)
    assert history.keys() == ()
    assert len(history) == 0


def test_boundary_below_max_survives() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    assert history.expire_stale(14.999, max_idle_seconds=5.0) == ()


def test_boundary_exact_max_survives() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    assert history.expire_stale(15.0, max_idle_seconds=5.0) == ()
    assert history.keys() == ((CAMERA_A, 1),)


def test_boundary_above_max_expires() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    assert history.expire_stale(15.001, max_idle_seconds=5.0) == ((CAMERA_A, 1),)


def test_expiry_uses_latest_timestamp_not_earliest() -> None:
    history = _history()
    history.append(_observation(timestamp=0.0))
    history.append(_observation(timestamp=19.0))
    # Earliest stamp is long stale (idle 20 > 5) but latest is fresh (idle 1).
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ()


def test_mixed_freshness_returns_only_stale_exact_tuple() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=0.0))
    history.append(_observation(track_id=2, timestamp=19.0))
    history.append(_observation(track_id=3, timestamp=1.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_A, 1), (CAMERA_A, 3))
    assert history.keys() == ((CAMERA_A, 2),)


def test_multi_camera_tracks_independent() -> None:
    history = _history()
    history.append(_observation(camera_id=CAMERA_A, track_id=1, timestamp=0.0))
    history.append(_observation(camera_id=CAMERA_B, track_id=1, timestamp=19.0))
    history.append(_observation(camera_id=CAMERA_A, track_id=2, timestamp=19.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_A, 1),)
    assert history.keys() == ((CAMERA_B, 1), (CAMERA_A, 2))


def test_empty_store_returns_empty() -> None:
    assert _history().expire_stale(100.0, max_idle_seconds=5.0) == ()


def test_repeated_cleanup_idempotent() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=0.0))
    history.append(_observation(track_id=2, timestamp=19.0))
    first = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert first == ((CAMERA_A, 1),)
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ()


def test_reuse_after_expiry_starts_fresh() -> None:
    history = _history()
    old = _observation(timestamp=0.0)
    history.append(old)
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ((CAMERA_A, 1),)
    fresh = _observation(timestamp=19.0)
    history.append(fresh)
    assert history.snapshot(CAMERA_A, 1) == (fresh,)
    assert old not in history.snapshot(CAMERA_A, 1)
    # Fresh history ages from the new append only.
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ()


def test_remove_recreate_ages_from_new_appends_only() -> None:
    history = _history()
    history.append(_observation(timestamp=0.0))
    assert history.remove(CAMERA_A, 1) is True
    history.append(_observation(timestamp=18.0))
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ()
    assert len(history.snapshot(CAMERA_A, 1)) == 1


def test_zero_max_idle_expires_only_positive_idle() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=20.0))
    history.append(_observation(track_id=2, timestamp=19.0))
    expired = history.expire_stale(20.0, max_idle_seconds=0.0)
    assert expired == ((CAMERA_A, 2),)
    assert history.keys() == ((CAMERA_A, 1),)


# --- fail-closed validation -------------------------------------------------


def test_invalid_now_inputs_fail_closed() -> None:
    bad_values: list[Any] = [
        None,
        True,
        False,
        "20.0",
        (20.0,),
        float("nan"),
        float("inf"),
        float("-inf"),
        -1.0,
        -0.5,
    ]
    for bad_now in bad_values:
        history = _history()
        kept = _observation(timestamp=10.0)
        history.append(kept)
        with pytest.raises((TypeError, ValueError)):
            history.expire_stale(bad_now, max_idle_seconds=5.0)
        assert history.snapshot(CAMERA_A, 1) == (kept,)
        assert history.keys() == ((CAMERA_A, 1),)


def test_invalid_max_idle_inputs_fail_closed() -> None:
    bad_values: list[Any] = [
        None,
        True,
        False,
        "5.0",
        (5.0,),
        float("nan"),
        float("inf"),
        float("-inf"),
        -1.0,
        -0.5,
    ]
    for bad_max in bad_values:
        history = _history()
        kept = _observation(timestamp=10.0)
        history.append(kept)
        with pytest.raises((TypeError, ValueError)):
            history.expire_stale(20.0, max_idle_seconds=bad_max)
        assert history.snapshot(CAMERA_A, 1) == (kept,)
        assert history.keys() == ((CAMERA_A, 1),)


def test_max_idle_keyword_only() -> None:
    history = _history()
    history.append(_observation(timestamp=10.0))
    with pytest.raises(TypeError):
        history.expire_stale(20.0, 5.0)  # type: ignore[misc]
    assert history.keys() == ((CAMERA_A, 1),)


# --- integrity / bulk / return contract -------------------------------------


def test_surviving_history_integrity() -> None:
    history = _history()
    survivor_obs = [_observation(track_id=2, timestamp=stamp) for stamp in (18.0, 19.0, 20.0)]
    for obs in survivor_obs:
        history.append(obs)
    history.append(_observation(track_id=1, timestamp=0.0))
    expired = history.expire_stale(21.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_A, 1),)
    assert history.snapshot(CAMERA_A, 2) == tuple(survivor_obs)


def test_bulk_reclamation() -> None:
    history = _history()
    count = 1000
    for track_id in range(count):
        history.append(_observation(track_id=track_id, timestamp=0.0))
    history.append(_observation(track_id=count, timestamp=19.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == tuple((CAMERA_A, track_id) for track_id in range(count))
    assert history.keys() == ((CAMERA_A, count),)
    assert len(history) == 1


def test_return_is_fresh_tuple() -> None:
    history = _history()
    history.append(_observation(timestamp=0.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert type(expired) is tuple
    assert all(type(key) is tuple for key in expired)
    assert expired == ((CAMERA_A, 1),)


def test_mutating_return_cannot_affect_store() -> None:
    history = _history()
    history.append(_observation(track_id=1, timestamp=0.0))
    history.append(_observation(track_id=2, timestamp=19.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == ((CAMERA_A, 1),)
    mutable = list(expired)
    mutable.clear()
    assert history.keys() == ((CAMERA_A, 2),)
    assert history.expire_stale(20.0, max_idle_seconds=5.0) == ()


def test_expiry_creates_no_keys() -> None:
    history = _history()
    assert history.expire_stale(50.0, max_idle_seconds=5.0) == ()
    assert history.keys() == ()
    assert len(history) == 0
    assert history.snapshot("never-seen", 999) == ()


def test_return_follows_insertion_order() -> None:
    history = _history()
    for track_id in (5, 3, 9, 1):
        history.append(_observation(track_id=track_id, timestamp=0.0))
    expired = history.expire_stale(20.0, max_idle_seconds=5.0)
    assert expired == tuple((CAMERA_A, track_id) for track_id in (5, 3, 9, 1))


# --- framework-freedom proofs -----------------------------------------------


def test_runtime_free_of_frameworks() -> None:
    before = set(sys.modules)
    history = _history()
    history.append(_observation(timestamp=1.0))
    history.expire_stale(10.0, max_idle_seconds=5.0)
    introduced = set(sys.modules) - before
    for module in _FORBIDDEN_RUNTIME_MODULES:
        assert module not in introduced, f"history path loaded forbidden module: {module}"


def test_ast_no_framework_imports_in_history() -> None:
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


def test_ast_no_framework_imports_in_this_test_module() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    roots: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.append(node.module.split(".")[0])
    assert not [root for root in roots if root in _FORBIDDEN_RUNTIME_MODULES]
