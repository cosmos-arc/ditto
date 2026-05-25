"""Factor evaluation module — metrics, report models, and evaluator."""

from ditto_features.evaluation.contracts import (
    ClosePriceProvider,
    ForwardReturnProvider,
    RiskFactorProvider,
)
from ditto_features.evaluation.evaluator._orchestrator import (
    EvaluationConfig,
    FactorEvaluator,
)

__all__ = [
    "ClosePriceProvider",
    "EvaluationConfig",
    "FactorEvaluator",
    "ForwardReturnProvider",
    "RiskFactorProvider",
]
