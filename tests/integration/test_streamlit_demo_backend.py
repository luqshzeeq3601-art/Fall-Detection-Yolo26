"""Streamlit demo backend: fall -> incident + snapshots -> AI opinion -> review -> export."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from app.core.backend import DemoBackend
from eldercare.fall_engine.state_machine.states import FallEvent


class _UnclearVLM:
    provider_name = "stub"
    model_name = "stub-vlm"

    async def generate_enrichment(
        self, prompt: str, media_path: str | None = None, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert media_path is not None and media_path.endswith("keyframe_00.jpg")
        return {
            "schema_version": "1.1.0",
            "posture_description": "Person on the floor",
            "environmental_context": "Room",
            "scene_summary": "Person on the floor next to a chair",
            "confidence_assessment": "low",
            "fall_assessment": "unclear",
        }


def _event() -> FallEvent:
    # Video-relative timestamps, as the demo produces them.
    return FallEvent(
        camera_id="live",
        track_id=1,
        confirmed_timestamp=4.0,
        candidate_timestamp=2.5,
        down_start_timestamp=3.5,
        features=None,  # type: ignore[arg-type]
        confidence=0.93,
    )


def test_demo_backend_end_to_end(tmp_path: Path) -> None:
    backend = DemoBackend(data_dir=tmp_path, provider=_UnclearVLM())
    frames = [np.full((48, 64, 3), v, np.uint8) for v in (10, 20, 30)]

    incident_id = backend.record_fall(_event(), "demo-fall-example-01", frames)

    view = None
    for _ in range(100):
        view = next(i for i in backend.list_incidents() if i.id == incident_id)
        if view.enrichment is not None:
            break
        time.sleep(0.02)
    assert view is not None and view.enrichment is not None

    # Re-stamped to wall-clock time (not 1970), onset gap preserved.
    assert abs(view.confirmed_at.timestamp() - time.time()) < 60
    assert view.camera_id == "demo-fall-example-01"
    assert [p.name for p in view.keyframes] == [
        "keyframe_00.jpg",
        "keyframe_01.jpg",
        "keyframe_02.jpg",
    ]
    assert all(p.is_file() for p in view.keyframes)
    assert view.enrichment.output["fall_assessment"] == "unclear"
    assert view.flagged_by_ai and view.needs_review

    backend.submit_review(incident_id, "non_fall", "tester", "")
    view = next(i for i in backend.list_incidents() if i.id == incident_id)
    assert not view.needs_review
    assert view.latest_review is not None and view.latest_review.notes is None

    text, count = backend.export_reviewed_jsonl()
    assert count == 1
    record = json.loads(text)
    assert record["human_label"] == "non_fall"
    assert record["vlm"]["fall_assessment"] == "unclear"


def test_demo_backend_without_vlm(tmp_path: Path) -> None:
    backend = DemoBackend(data_dir=tmp_path, provider=None)
    assert not backend.vlm_enabled and backend.vlm_label == "Off"
    incident_id = backend.record_fall(_event(), "demo-cam", [])
    (view,) = backend.list_incidents()
    assert view.id == incident_id and view.enrichment is None and view.keyframes == ()
