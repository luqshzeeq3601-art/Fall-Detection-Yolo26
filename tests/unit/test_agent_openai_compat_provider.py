"""Unit tests for OpenAICompatVLMProvider and the schema 1.1.0 fall verdict."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from eldercare.agents.client import (
    OpenAICompatVLMProvider,
    ProviderConfig,
    ProviderMalformedResponseError,
)
from eldercare.agents.prompts import DEFAULT_PROMPT_VERSION, build_enrichment_prompt
from eldercare.agents.schemas import (
    FallAssessment,
    enrichment_needs_review,
    parse_and_validate_enrichment_output,
)

_VALID_OUTPUT: dict[str, Any] = {
    "schema_version": "1.1.0",
    "posture_description": "Person lying on side on the floor",
    "apparent_motion_context": None,
    "environmental_context": "Kitchen with tiled floor",
    "scene_summary": "Person on kitchen floor",
    "confidence_assessment": "medium",
    "uncertainty_factors": [],
    "postural_state": "lying_floor",
    "potential_hazards": [],
    "fall_assessment": "fall",
}


def _provider(handler: Any) -> OpenAICompatVLMProvider:
    config = ProviderConfig(
        provider_name="ollama",
        model="local-vlm",
        base_url="http://localhost:11434",
        max_retries=0,
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatVLMProvider(config=config, client=client)


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.mark.asyncio
async def test_sends_image_as_data_url_and_parses_json_content(tmp_path: Path) -> None:
    image = tmp_path / "keyframe_00.jpg"
    image.write_bytes(b"\xff\xd8\xff-fake-jpeg")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return _chat_response(json.dumps(_VALID_OUTPUT))

    result = await _provider(handler).generate_enrichment(
        prompt="describe", media_path=str(image)
    )

    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    body = seen["body"]
    assert body["model"] == "local-vlm"
    assert body["response_format"] == {"type": "json_object"}
    parts = body["messages"][0]["content"]
    assert parts[0] == {"type": "text", "text": "describe"}
    expected_b64 = base64.b64encode(image.read_bytes()).decode("ascii")
    assert parts[1]["image_url"]["url"] == f"data:image/jpeg;base64,{expected_b64}"
    assert result == _VALID_OUTPUT


@pytest.mark.asyncio
async def test_non_image_media_is_not_sent(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x00")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _chat_response(json.dumps(_VALID_OUTPUT))

    await _provider(handler).generate_enrichment(
        prompt="describe", media_path=str(clip)
    )
    assert len(seen["body"]["messages"][0]["content"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"choices": []},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": "[1, 2]"}}]},
    ],
)
async def test_malformed_chat_responses_raise(payload: dict[str, Any]) -> None:
    provider = _provider(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(ProviderMalformedResponseError):
        await provider.generate_enrichment(prompt="describe")


def test_default_prompt_requests_fall_assessment() -> None:
    assert DEFAULT_PROMPT_VERSION == "v1.1.0"
    prompt = build_enrichment_prompt(context={"incident_id": "inc-1"})
    assert '"fall_assessment"' in prompt
    assert '"schema_version": "1.1.0"' in prompt


def test_schema_accepts_1_1_0_with_fall_assessment_and_still_accepts_1_0_0() -> None:
    parsed = parse_and_validate_enrichment_output(_VALID_OUTPUT)
    assert parsed.fall_assessment is FallAssessment.FALL

    legacy = {k: v for k, v in _VALID_OUTPUT.items() if k != "fall_assessment"}
    legacy["schema_version"] = "1.0.0"
    assert parse_and_validate_enrichment_output(legacy).fall_assessment is None


def test_schema_rejects_unsupported_version() -> None:
    with pytest.raises(ProviderMalformedResponseError):
        parse_and_validate_enrichment_output(
            {**_VALID_OUTPUT, "schema_version": "9.9.9"}
        )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, False),
        ({"confidence_assessment": "uncertain"}, True),
        ({"fall_assessment": "no_fall"}, True),
        ({"fall_assessment": "unclear"}, True),
        ({"fall_assessment": None}, False),
    ],
)
def test_enrichment_needs_review(overrides: dict[str, Any], expected: bool) -> None:
    assert enrichment_needs_review({**_VALID_OUTPUT, **overrides}) is expected


def test_enrichment_needs_review_handles_missing_output() -> None:
    assert enrichment_needs_review(None) is False
