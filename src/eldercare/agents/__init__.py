"""ElderCare Vision agents subpackage."""

from eldercare.agents.client import (
    HTTPVLMProvider,
    MockVLMProvider,
    OpenAICompatVLMProvider,
    ProviderAuthError,
    ProviderClientError,
    ProviderConfig,
    ProviderConnectionError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    VLMProvider,
)
from eldercare.agents.evaluation import (
    STANDARD_BENCHMARK_SCENARIOS,
    AgentQualityEvaluator,
    ScenarioDefinition,
    ScenarioEvaluationResult,
    SuiteEvaluationSummary,
)
from eldercare.agents.orchestrator import AgentEnrichmentOrchestrator
from eldercare.agents.privacy import EvidencePrivacyBoundary
from eldercare.agents.prompts import (
    DEFAULT_PROMPT_VERSION,
    build_enrichment_prompt,
    list_supported_prompt_versions,
)
from eldercare.agents.schemas import (
    ConfidenceLevel,
    EnrichmentOutputSchema,
    FallAssessment,
    PosturalState,
    enrichment_needs_review,
    parse_and_validate_enrichment_output,
)
from eldercare.agents.service import AsyncEnrichmentService
from eldercare.agents.state import EnrichmentJob, EnrichmentStatus

__all__ = [
    "DEFAULT_PROMPT_VERSION",
    "STANDARD_BENCHMARK_SCENARIOS",
    "AgentEnrichmentOrchestrator",
    "AgentQualityEvaluator",
    "AsyncEnrichmentService",
    "ConfidenceLevel",
    "EnrichmentJob",
    "EnrichmentOutputSchema",
    "EnrichmentStatus",
    "EvidencePrivacyBoundary",
    "FallAssessment",
    "HTTPVLMProvider",
    "MockVLMProvider",
    "OpenAICompatVLMProvider",
    "PosturalState",
    "ProviderAuthError",
    "ProviderClientError",
    "ProviderConfig",
    "ProviderConnectionError",
    "ProviderMalformedResponseError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ScenarioDefinition",
    "ScenarioEvaluationResult",
    "SuiteEvaluationSummary",
    "VLMProvider",
    "build_enrichment_prompt",
    "enrichment_needs_review",
    "list_supported_prompt_versions",
    "parse_and_validate_enrichment_output",
]
