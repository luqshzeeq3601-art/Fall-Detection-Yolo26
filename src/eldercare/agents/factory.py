"""Environment-driven construction of the Agent/VLM provider."""

from __future__ import annotations

import os
from collections.abc import Mapping

from eldercare.agents.client import (
    HTTPVLMProvider,
    MockVLMProvider,
    OpenAICompatVLMProvider,
    ProviderConfig,
    VLMProvider,
)

SUPPORTED_VLM_PROVIDERS = ("none", "mock", "openai_compat", "http")


def build_vlm_provider_from_env(
    env: Mapping[str, str] | None = None,
) -> VLMProvider | None:
    """Build the VLM provider selected by ``VLM_PROVIDER``.

    ``VLM_PROVIDER``:
        - ``none`` (default): enrichment disabled, returns None.
        - ``mock``: canned output, for local development only.
        - ``openai_compat``: on-prem OpenAI-compatible server (Ollama, vLLM).
        - ``http``: legacy ``/v1/enrich`` endpoint.

    Remote providers read ``VLM_BASE_URL``, ``VLM_MODEL``, ``VLM_API_KEY``,
    ``VLM_TIMEOUT_SECONDS`` and ``VLM_MAX_RETRIES``.

    Raises:
        ValueError: on an unknown provider or a non-numeric timeout/retry value.
    """
    env = os.environ if env is None else env
    kind = env.get("VLM_PROVIDER", "none").strip().lower()

    if kind == "none":
        return None
    if kind == "mock":
        return MockVLMProvider()
    if kind not in SUPPORTED_VLM_PROVIDERS:
        raise ValueError(
            f"Unknown VLM_PROVIDER '{kind}'. Supported: {', '.join(SUPPORTED_VLM_PROVIDERS)}"
        )

    config = ProviderConfig(
        provider_name=kind,
        model=env.get("VLM_MODEL", "vlm-default"),
        base_url=env.get("VLM_BASE_URL", "http://localhost:11434"),
        api_key=env.get("VLM_API_KEY") or None,
        timeout_seconds=float(env.get("VLM_TIMEOUT_SECONDS", "5.0")),
        max_retries=int(env.get("VLM_MAX_RETRIES", "2")),
    )
    if kind == "openai_compat":
        return OpenAICompatVLMProvider(config=config)
    return HTTPVLMProvider(config=config)
