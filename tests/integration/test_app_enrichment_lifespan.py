"""App startup wiring: VLM provider from env, enrichment workers, bridge, review queue API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from eldercare.agents.client import (
    HTTPVLMProvider,
    MockVLMProvider,
    OpenAICompatVLMProvider,
)
from eldercare.agents.factory import build_vlm_provider_from_env
from eldercare.api.app import build_fall_incident_bridge, create_app
from eldercare.db.base import Base
from eldercare.evidence.storage import EvidenceStorage
from eldercare.fall_engine.state_machine.states import FallEvent


class _NoFallVLM:
    provider_name = "no-fall-vlm"
    model_name = "stub-v1"

    async def generate_enrichment(
        self,
        prompt: str,
        media_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.1.0",
            "posture_description": "Person kneeling to pick something up",
            "environmental_context": "Bedroom",
            "scene_summary": "Person kneeling, not fallen",
            "confidence_assessment": "high",
            "fall_assessment": "no_fall",
        }


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _event() -> FallEvent:
    now = time.time()
    return FallEvent(
        camera_id="cam-bedroom",
        track_id=3,
        confirmed_timestamp=now,
        candidate_timestamp=now - 2.0,
        down_start_timestamp=now - 1.0,
        features=None,  # type: ignore[arg-type]
        confidence=0.88,
    )


def test_startup_runs_enrichment_and_exposes_review_queue(
    session_factory: Any, tmp_path: Path
) -> None:
    app = create_app(
        session_factory=session_factory,
        evidence_storage=EvidenceStorage(base_dir=tmp_path / "evidence"),
        vlm_provider=_NoFallVLM(),
    )

    with TestClient(app) as client:
        assert app.state.enrichment_service is not None
        assert app.state.enrichment_service.is_running

        bridge = build_fall_incident_bridge(
            app, model_name="v6_3_phase3b", model_version="6.3", config_version="test"
        )
        incident = bridge.handle_fall_event(_event(), [np.zeros((32, 32, 3), np.uint8)])

        detail: dict[str, Any] = {}
        for _ in range(100):
            detail = client.get(f"/incidents/{incident.id}").json()
            if detail.get("enrichments"):
                break
            time.sleep(0.02)
        assert detail["enrichments"][0]["status"] == "completed"
        assert detail["enrichments"][0]["output"]["fall_assessment"] == "no_fall"

        queue = client.get("/incidents", params={"needs_review": "true"}).json()
        assert [item["id"] for item in queue["items"]] == [incident.id]

        client.post(
            f"/incidents/{incident.id}/reviews",
            json={"label": "non_fall", "reviewer": "nurse-1"},
        )
        assert (
            client.get("/incidents", params={"needs_review": "true"}).json()["total"]
            == 0
        )

    assert app.state.enrichment_service is None


def test_enrichment_disabled_by_default(
    session_factory: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("VLM_PROVIDER", raising=False)
    app = create_app(
        session_factory=session_factory,
        evidence_storage=EvidenceStorage(base_dir=tmp_path / "evidence"),
    )

    with TestClient(app):
        assert app.state.enrichment_service is None
        bridge = build_fall_incident_bridge(
            app, model_name="m", model_version="v", config_version="c"
        )
        incident = bridge.handle_fall_event(_event())
        assert incident.id


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, type(None)),
        ({"VLM_PROVIDER": "none"}, type(None)),
        ({"VLM_PROVIDER": "mock"}, MockVLMProvider),
        ({"VLM_PROVIDER": "openai_compat"}, OpenAICompatVLMProvider),
        ({"VLM_PROVIDER": "HTTP"}, HTTPVLMProvider),
    ],
)
def test_build_vlm_provider_from_env(env: dict[str, str], expected: type) -> None:
    assert isinstance(build_vlm_provider_from_env(env), expected)


def test_build_vlm_provider_reads_connection_settings() -> None:
    provider = build_vlm_provider_from_env(
        {
            "VLM_PROVIDER": "openai_compat",
            "VLM_BASE_URL": "http://gpu-box:8000",
            "VLM_MODEL": "local-vlm",
            "VLM_TIMEOUT_SECONDS": "12.5",
            "VLM_MAX_RETRIES": "1",
        }
    )
    assert isinstance(provider, OpenAICompatVLMProvider)
    assert provider.config.base_url == "http://gpu-box:8000"
    assert provider.model_name == "local-vlm"
    assert provider.config.timeout_seconds == 12.5
    assert provider.config.max_retries == 1


def test_build_vlm_provider_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unknown VLM_PROVIDER"):
        build_vlm_provider_from_env({"VLM_PROVIDER": "cloud-magic"})
