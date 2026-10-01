"""Unit tests for Agent/VLM Provider Client (P10-003).

Validates:
- Domain error hierarchy and secret redaction.
- ProviderConfig masking and immutability.
- MockVLMProvider deterministic behavior and fault injection.
- HTTPVLMProvider retry gating, timeout enforcement, backoff calculation,
  auth rejection without retry, and malformed payload handling.
"""

from __future__ import annotations

import httpx
import pytest

from eldercare.agents.client import (
    HTTPVLMProvider,
    MockVLMProvider,
    ProviderAuthError,
    ProviderClientError,
    ProviderConfig,
    ProviderConnectionError,
    ProviderMalformedResponseError,
    ProviderTimeoutError,
    VLMProvider,
)

# =====================================================================
# Error Hierarchy & Secret Masking Tests
# =====================================================================


def test_provider_client_error_masks_secrets() -> None:
    secret = "sk-super-secret-key-12345678"
    err = ProviderClientError(f"Failed with api_key={secret} on http://user:pass123@api.vlm.com")
    assert secret not in str(err)
    assert "pass123" not in str(err)
    assert "***" in str(err)


def test_provider_config_masks_api_key_in_repr() -> None:
    config = ProviderConfig(
        provider_name="test-vlm",
        api_key="secret-api-token-987654321",
        base_url="https://api.vlm.service.com",
    )
    repr_str = repr(config)
    assert "secret-api-token-987654321" not in repr_str
    assert "se***21" in repr_str or "***" in repr_str


# =====================================================================
# MockVLMProvider Tests
# =====================================================================


@pytest.mark.asyncio
async def test_mock_vlm_provider_protocol_and_generation() -> None:
    provider = MockVLMProvider(
        provider_name="mock-test",
        model_name="mock-v1",
        default_response={"scene_summary": "Test scene summary", "schema_version": "1.0.0"},
    )
    assert isinstance(provider, VLMProvider)
    assert provider.provider_name == "mock-test"
    assert provider.model_name == "mock-v1"

    res = await provider.generate_enrichment(
        prompt="Describe scene",
        media_path="/tmp/test.jpg",
        context={"camera_id": "cam-1"},
    )
    assert res["scene_summary"] == "Test scene summary"
    assert provider.call_count == 1
    assert provider.calls[0]["media_path"] == "/tmp/test.jpg"


@pytest.mark.asyncio
async def test_mock_vlm_provider_error_injection() -> None:
    provider = MockVLMProvider(
        errors_to_raise=[
            ProviderTimeoutError("Simulated timeout"),
            ProviderAuthError("Simulated auth rejection"),
        ]
    )
    with pytest.raises(ProviderTimeoutError):
        await provider.generate_enrichment(prompt="test")

    with pytest.raises(ProviderAuthError):
        await provider.generate_enrichment(prompt="test")

    # Next call returns default response
    res = await provider.generate_enrichment(prompt="test")
    assert res["schema_version"] == "1.0.0"


# =====================================================================
# HTTPVLMProvider Tests with Mock Transport
# =====================================================================


@pytest.mark.asyncio
async def test_http_vlm_provider_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/enrich"
        assert request.headers.get("Authorization") == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "scene_summary": "Subject resting safely on sofa",
                "confidence_assessment": "high",
                "schema_version": "1.0.0",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            api_key="test-key",
            base_url="http://test-vlm-service",
            timeout_seconds=2.0,
            max_retries=1,
        )
        provider = HTTPVLMProvider(config=config, client=client)
        result = await provider.generate_enrichment(
            prompt="Analyze posture",
            media_path="/data/evidence/test.jpg",
            context={"fall_detected": True},
        )
        assert result["scene_summary"] == "Subject resting safely on sofa"
        assert result["schema_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_http_vlm_provider_auth_error_no_retry() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, text="Unauthorized: Invalid API Key")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            api_key="invalid-key",
            max_retries=3,  # Should NOT retry 401
        )
        provider = HTTPVLMProvider(config=config, client=client)

        with pytest.raises(ProviderAuthError) as exc_info:
            await provider.generate_enrichment(prompt="Test")

        assert exc_info.value.status_code == 401
        assert call_count == 1  # No retries for 401


@pytest.mark.asyncio
async def test_http_vlm_provider_client_syntax_error_no_retry() -> None:
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(422, text="Unprocessable Entity: prompt too long")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            max_retries=3,
        )
        provider = HTTPVLMProvider(config=config, client=client)

        with pytest.raises(ProviderClientError) as exc_info:
            await provider.generate_enrichment(prompt="Too long prompt")

        assert exc_info.value.status_code == 422
        assert call_count == 1


@pytest.mark.asyncio
async def test_http_vlm_provider_rate_limit_retry_and_recovery() -> None:
    call_count = 0
    sleeps: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0.2"}, text="Too Many Requests")
        return httpx.Response(
            200,
            json={"scene_summary": "Recovered after 429", "schema_version": "1.0.0"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            max_retries=2,
            backoff_factor=0.1,
        )
        provider = HTTPVLMProvider(config=config, client=client, sleep_func=mock_sleep)
        res = await provider.generate_enrichment(prompt="Test")
        assert res["scene_summary"] == "Recovered after 429"
        assert call_count == 2
        assert sleeps == [0.2]


@pytest.mark.asyncio
async def test_http_vlm_provider_transient_503_exhaust_retries() -> None:
    call_count = 0
    sleeps: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            max_retries=2,
            backoff_factor=0.2,
        )
        provider = HTTPVLMProvider(config=config, client=client, sleep_func=mock_sleep)

        with pytest.raises(ProviderConnectionError) as exc_info:
            await provider.generate_enrichment(prompt="Test")

        assert exc_info.value.status_code == 503
        assert call_count == 3  # 1 initial + 2 retries
        assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_http_vlm_provider_timeout_exception() -> None:
    call_count = 0
    sleeps: list[float] = []

    async def mock_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("Socket read timed out")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(
            provider_name="mock-http",
            max_retries=1,
            timeout_seconds=1.5,
        )
        provider = HTTPVLMProvider(config=config, client=client, sleep_func=mock_sleep)

        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.generate_enrichment(prompt="Test")

        assert "timed out" in str(exc_info.value)
        assert call_count == 2
        assert len(sleeps) == 1


@pytest.mark.asyncio
async def test_http_vlm_provider_malformed_json_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<HTML>Not JSON</HTML>",
            headers={"Content-Type": "text/html"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        config = ProviderConfig(provider_name="mock-http", max_retries=1)
        provider = HTTPVLMProvider(config=config, client=client)

        with pytest.raises(ProviderMalformedResponseError) as exc_info:
            await provider.generate_enrichment(prompt="Test")

        assert "JSON" in str(exc_info.value)
