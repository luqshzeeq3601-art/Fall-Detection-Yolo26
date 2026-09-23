"""ElderCare Vision fall_engine subpackage."""

from eldercare.fall_engine.confidence import (
    CooldownConfig,
    FallConfidenceBreakdown,
    FallConfidenceConfig,
    IncidentCooldownManager,
    compute_fall_confidence,
)
from eldercare.fall_engine.evaluation import (
    EvaluationMetrics,
    SequenceEvalResult,
    SequenceEvaluationRunner,
    SequenceManifestRecord,
    compute_metrics,
    load_manifest,
    validate_manifest_integrity,
)
from eldercare.fall_engine.features import (
    PoseGeometryFeatures,
    TemporalFeatures,
    extract_geometry_features,
    extract_temporal_features,
)
from eldercare.fall_engine.state_machine import (
    FallEvent,
    FallState,
    FallStateMachineConfig,
    FallStateMachineManager,
    FallStateTransition,
    TrackFallStateMachine,
)

__all__ = [
    "CooldownConfig",
    "EvaluationMetrics",
    "FallConfidenceBreakdown",
    "FallConfidenceConfig",
    "FallEvent",
    "FallState",
    "FallStateMachineConfig",
    "FallStateMachineManager",
    "FallStateTransition",
    "IncidentCooldownManager",
    "PoseGeometryFeatures",
    "SequenceEvalResult",
    "SequenceEvaluationRunner",
    "SequenceManifestRecord",
    "TemporalFeatures",
    "TrackFallStateMachine",
    "compute_fall_confidence",
    "compute_metrics",
    "extract_geometry_features",
    "extract_temporal_features",
    "load_manifest",
    "validate_manifest_integrity",
]
