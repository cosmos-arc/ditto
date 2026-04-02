"""
Factor evaluation metrics -- pure Polars vectorized computations.

All functions are stateless, side-effect free, and depend only on ``polars``
and the standard library.  They accept / return ``pl.DataFrame`` or simple
Python containers.

This package re-exports every public symbol so that existing import paths
such as ``from ditto_analytics.evaluation.metrics import X`` continue to
work without modification.
"""

from ._math import EvaluationColumns

# Re-export private helpers for backward compatibility (used in tests).
from ._math import scalar_to_float as _scalar_to_float
from ._math import two_sided_p_value as _two_sided_p_value
from .factor_analysis import (
    factor_exposure,
    fama_macbeth,
    orthogonalize,
    performance_attribution,
)
from .ic import (
    ic_autocorrelation,
    ic_decay,
    ic_momentum,
    ic_summary,
    pearson_ic,
    rank_ic,
    regime_adjusted_ic,
    sub_period_ic,
)
from .portfolio import (
    long_short_returns,
    net_returns,
    quantile_returns,
    turnover,
    turnover_adjusted_ir,
)
from .tail_risk import grinold_kahn_ir, tail_risk_metrics

__all__ = [
    "EvaluationColumns",
    "_scalar_to_float",
    "_two_sided_p_value",
    "factor_exposure",
    "fama_macbeth",
    "grinold_kahn_ir",
    "ic_autocorrelation",
    "ic_decay",
    "ic_momentum",
    "ic_summary",
    "long_short_returns",
    "net_returns",
    "orthogonalize",
    "pearson_ic",
    "performance_attribution",
    "quantile_returns",
    "rank_ic",
    "regime_adjusted_ic",
    "sub_period_ic",
    "tail_risk_metrics",
    "turnover",
    "turnover_adjusted_ir",
]
