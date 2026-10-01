"""Evaluation harness, dataset manifest tools, and V4 metrics guardrails."""

from eldercare.fall_engine.evaluation.guardrails import (
    HardcodedGateValueDetector,
    LabelLeakageDetector,
    MetricIntegrityGuard,
)
from eldercare.fall_engine.evaluation.manifest import (
    SequenceManifestRecord,
    load_manifest,
    validate_manifest_integrity,
)
from eldercare.fall_engine.evaluation.metrics import (
    EvaluationMetrics,
    compute_metrics,
)
from eldercare.fall_engine.evaluation.metrics_v4 import (
    DeploymentMetricsV4,
    V4EvaluationResult,
    check_deployment_gates_v4,
    compute_deployment_metrics_v4,
    compute_poisson_confidence_interval,
)
from eldercare.fall_engine.evaluation.runner import (
    SequenceEvalResult,
    SequenceEvaluationRunner,
)
from eldercare.fall_engine.evaluation.split_guard import (
    DatasetSplitGuard,
    HoldoutAccessError,
    SplitLeakageError,
)

__all__ = [
    "DatasetSplitGuard",
    "DeploymentMetricsV4",
    "EvaluationMetrics",
    "HardcodedGateValueDetector",
    "HoldoutAccessError",
    "LabelLeakageDetector",
    "MetricIntegrityGuard",
    "SequenceEvalResult",
    "SequenceEvaluationRunner",
    "SequenceManifestRecord",
    "SplitLeakageError",
    "V4EvaluationResult",
    "check_deployment_gates_v4",
    "compute_deployment_metrics_v4",
    "compute_metrics",
    "compute_poisson_confidence_interval",
    "load_manifest",
    "validate_manifest_integrity",
]
