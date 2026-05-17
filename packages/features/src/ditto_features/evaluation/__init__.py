"""Factor evaluation module — metrics, report models, and evaluator."""

from ditto_features.evaluation.contracts import (
    ClosePriceProvider,
    ForwardReturnProvider,
    RiskFactorProvider,
)
from ditto_features.evaluation.report import (
    FactorEvaluationReport,
    FactorExposureResult,
    FamaMacBethResult,
    ICSummary,
    LongShortResult,
    PerformanceAttributionResult,
    RegimeICResult,
    TailRiskMetrics,
)

__all__ = [
    "ClosePriceProvider",
    "FactorEvaluationReport",
    "FactorExposureResult",
    "FamaMacBethResult",
    "ForwardReturnProvider",
    "ICSummary",
    "LongShortResult",
    "PerformanceAttributionResult",
    "RegimeICResult",
    "RiskFactorProvider",
    "TailRiskMetrics",
]
