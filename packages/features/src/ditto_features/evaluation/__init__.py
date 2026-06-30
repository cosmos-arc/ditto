"""Factor evaluation module — metrics, report models, and evaluator."""

from ditto_features.evaluation.contracts import (
    ClosePriceProvider,
    ForwardReturnProvider,
    RiskFactorProvider,
)
from ditto_features.evaluation.report import (
    AttributionContribution,
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
    "AttributionContribution",
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
