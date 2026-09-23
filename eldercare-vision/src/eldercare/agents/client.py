"""Provider client abstractions, resilient HTTP client, and mock provider for Agent/VLM (P10-003).

Provides:
- Normalized error hierarchy.
- Protocol definition (VLMProvider).
- Deterministic MockVLMProvider for testing and offline development.
- Resilient HTTPVLMProvider with strict per-request timeouts, bounded exponential backoff retries,
  transient error gating, and fail-closed secret redaction.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from eldercare.common.logger import get_logger
from eldercare.common.redaction import redact_token, sanitize_exception_message

logger = get_logger("eldercare.agents.client")


# =====================================================================
# Error Hierarchy
# =====================================================================


class ProviderClientError(Exception):
    """Base exception for all Agent/VLM provider client errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        provider: str | None = None,
        raw_error: Exception | None = None,
    ) -> None:
        self.raw_message = message
        self.status_code = status_code
        self.provider = provider
        self.raw_error = raw_error
        # Redact any accidental credential leaks in message
        sanitized = sanitize_exception_message(message)
        super().__init__(sanitized)

    def __repr__(self) -> str:
        name = self.__class__.__name__
        sanitized_msg = sanitize_exception_message(self.raw_message)
        return (
            f"{name}(message={sanitized_msg!r}, status_code={self.status_code}, "
            f"provider={self.provider!r})"
        )


class ProviderTimeoutError(ProviderClientError):
    """Raised when an Agent/VLM provider request times out."""


class ProviderRateLimitError(ProviderClientError):
    """Raised when an Agent/VLM provider returns HTTP 429 Too Many Requests."""

    def __init__(
        self,
        message: str,
        retry_after: float | None = None,
        provider: str | None = None,
        raw_error: Exception | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=429,
            provider=provider,
            raw_error=raw_error,
        )
        self.retry_after = retry_after


class ProviderAuthError(ProviderClientError):
    """Raised on authentication/authorization rejection (HTTP 401/403). Never retried."""


class ProviderMalformedResponseError(ProviderClientError):
    """Raised when the provider response cannot be parsed or lacks required fields."""


class ProviderConnectionError(ProviderClientError):
    """Raised on transport, DNS, or connection drop failures."""


# =====================================================================
# Configuration
# =====================================================================


@dataclass
class ProviderConfig:
    """Configuration for an Agent/VLM provider client."""

    provider_name: str = "mock"
    model: str = "vlm-default"
    base_url: str = "http://localhost:8000"
    api_key: str | None = None
    timeout_seconds: float = 5.0
    max_retries: int = 2
    backoff_factor: float = 0.5
    max_backoff: float = 2.0

    def __repr__(self) -> str:
        masked_key = redact_token(self.api_key) if self.api_key else None
        return (
            f"ProviderConfig(provider_name={self.provider_name!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key={masked_key!r}, "
            f"timeout_seconds={self.timeout_seconds}, max_retries={self.max_retries}, "
            f"backoff_factor={self.backoff_factor}, max_backoff={self.max_backoff})"
        )


# =====================================================================
# Provider Protocol
# =====================================================================


@runtime_checkable
class VLMProvider(Protocol):
    """Protocol contract for vision-language model enrichment providers."""

    @property
    def provider_name(self) -> str:
        """Return provider identifier name."""
        ...

    @property
    def model_name(self) -> str:
        """Return model identifier name."""
        ...

    async def generate_enrichment(
        self,
        prompt: str,
        media_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate structured enrichment dictionary from prompt and visual/metadata inputs.

        Raises:
            ProviderClientError: on failure.
        """
        ...


# =====================================================================
# Mock Provider
# =====================================================================


class MockVLMProvider:
    """Deterministic, programmable in-memory VLM provider for tests and hermetic execution."""

    def __init__(
        self,
        provider_name: str = "mock-vlm",
        model_name: str = "mock-model-v1",
        default_response: dict[str, Any] | None = None,
        simulated_latency_seconds: float = 0.0,
        errors_to_raise: list[Exception] | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._model_name = model_name
        self._default_response = default_response or {
            "posture_description": "Person lying on floor near chair",
            "apparent_motion_context": "Rapid descent detected prior to resting state",
            "environmental_context": "Living room with area rug and arm chair",
            "scene_summary": "Subject fell and remains on floor; immediate attention advised",
            "confidence_assessment": "high",
            "uncertainty_factors": [],
            "schema_version": "1.0.0",
        }
        self._simulated_latency_seconds = simulated_latency_seconds
        self._errors_to_raise = list(errors_to_raise or [])
        self._calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self._calls

    @property
    def call_count(self) -> int:
        return len(self._calls)

    async def generate_enrichment(
        self,
        prompt: str,
        media_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._calls.append(
            {
                "prompt": prompt,
                "media_path": media_path,
                "context": context,
            }
        )

        if self._simulated_latency_seconds > 0:
            await asyncio.sleep(self._simulated_latency_seconds)

        if self._errors_to_raise:
            err = self._errors_to_raise.pop(0)
            raise err

        return dict(self._default_response)


# =====================================================================
# HTTP Provider Client
# =====================================================================


class HTTPVLMProvider:
    """Asynchronous HTTP VLM provider client with retry, timeout, and secret masking."""

    def __init__(
        self,
        config: ProviderConfig,
        client: httpx.AsyncClient | None = None,
        sleep_func: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._sleep_func = sleep_func or asyncio.sleep

    @property
    def provider_name(self) -> str:
        return self.config.provider_name

    @property
    def model_name(self) -> str:
        return self.config.model

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with ceiling."""
        delay = self.config.backoff_factor * (2 ** (attempt - 1))
        return min(delay, self.config.max_backoff)

    async def generate_enrichment(
        self,
        prompt: str,
        media_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send prompt to VLM endpoint and return parsed JSON result.

        Retries transient errors (timeouts, connection drops, 429, 502, 503, 504)
        up to `max_retries` times. Never retries 400, 401, 403, 422.
        """
        payload: dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
        }
        if media_path is not None:
            payload["media_path"] = media_path
        if context is not None:
            payload["context"] = context

        url = f"{self.config.base_url.rstrip('/')}/v1/enrich"
        headers = self._get_headers()
        max_attempts = 1 + max(0, self.config.max_retries)

        last_exception: Exception | None = None

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.config.timeout_seconds)

        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.debug(
                        "Dispatching VLM enrichment request",
                        extra={
                            "provider": self.provider_name,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                        },
                    )
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                    )

                    # Success path
                    if 200 <= response.status_code < 300:
                        try:
                            data = response.json()
                        except Exception as exc:
                            raise ProviderMalformedResponseError(
                                message=f"Failed to parse JSON response: {exc}",
                                status_code=response.status_code,
                                provider=self.provider_name,
                                raw_error=exc,
                            ) from exc

                        if not isinstance(data, dict):
                            raise ProviderMalformedResponseError(
                                message=f"Expected JSON object, got {type(data).__name__}",
                                status_code=response.status_code,
                                provider=self.provider_name,
                            )
                        return data

                    # Non-2xx response handling
                    status = response.status_code
                    text_snippet = response.text[:200]

                    # Auth errors (401, 403) -> Fail fast, never retry
                    if status in (401, 403):
                        raise ProviderAuthError(
                            message=f"Auth failed with HTTP {status}: {text_snippet}",
                            status_code=status,
                            provider=self.provider_name,
                        )

                    # Client syntax/validation error (400, 422) -> Non-retriable
                    if status in (400, 422):
                        raise ProviderClientError(
                            message=f"Request rejected with HTTP {status}: {text_snippet}",
                            status_code=status,
                            provider=self.provider_name,
                        )

                    # Rate limited (429) -> Retriable
                    if status == 429:
                        retry_after_hdr = response.headers.get("Retry-After")
                        retry_after: float | None = None
                        if retry_after_hdr:
                            try:
                                retry_after = float(retry_after_hdr)
                            except ValueError:
                                retry_after = None

                        rate_err = ProviderRateLimitError(
                            message=f"Provider rate limited (HTTP 429): {text_snippet}",
                            retry_after=retry_after,
                            provider=self.provider_name,
                        )
                        last_exception = rate_err
                        if attempt < max_attempts:
                            delay = (
                                retry_after
                                if retry_after is not None
                                else self._calculate_backoff(attempt)
                            )
                            logger.warning(
                                "VLM rate limited; backing off",
                                extra={"attempt": attempt, "backoff_seconds": delay},
                            )
                            await self._sleep_func(delay)
                            continue
                        raise rate_err

                    # Server / Gateway errors (500, 502, 503, 504) -> Retriable
                    if status in (500, 502, 503, 504):
                        conn_err = ProviderConnectionError(
                            message=f"Server returned transient HTTP {status}: {text_snippet}",
                            status_code=status,
                            provider=self.provider_name,
                        )
                        last_exception = conn_err
                        if attempt < max_attempts:
                            delay = self._calculate_backoff(attempt)
                            logger.warning(
                                "Transient server error; backing off",
                                extra={
                                    "status": status,
                                    "attempt": attempt,
                                    "backoff_seconds": delay,
                                },
                            )
                            await self._sleep_func(delay)
                            continue
                        raise conn_err

                    # Other unhandled HTTP status
                    raise ProviderClientError(
                        message=f"HTTP request failed with status {status}: {text_snippet}",
                        status_code=status,
                        provider=self.provider_name,
                    )

                except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                    timeout_err = ProviderTimeoutError(
                        message=f"Request timed out after {self.config.timeout_seconds}s",
                        status_code=None,
                        provider=self.provider_name,
                        raw_error=exc,
                    )
                    last_exception = timeout_err
                    if attempt < max_attempts:
                        delay = self._calculate_backoff(attempt)
                        logger.warning(
                            "VLM request timed out; retrying",
                            extra={"attempt": attempt, "backoff_seconds": delay},
                        )
                        await self._sleep_func(delay)
                        continue
                    raise timeout_err from exc

                except (httpx.NetworkError, httpx.ConnectError) as exc:
                    conn_err = ProviderConnectionError(
                        message=f"Network transport error: {exc}",
                        status_code=None,
                        provider=self.provider_name,
                        raw_error=exc,
                    )
                    last_exception = conn_err
                    if attempt < max_attempts:
                        delay = self._calculate_backoff(attempt)
                        logger.warning(
                            "VLM connection failure; retrying",
                            extra={"attempt": attempt, "backoff_seconds": delay},
                        )
                        await self._sleep_func(delay)
                        continue
                    raise conn_err from exc

            # If we exited the loop without returning or raising
            if last_exception is not None:
                raise last_exception
            raise ProviderClientError(
                message="Retries exhausted without response",
                provider=self.provider_name,
            )

        finally:
            if owns_client:
                await client.aclose()
