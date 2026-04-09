"""因子规格聚合注册表."""

from __future__ import annotations

from ditto_analytics.factors.alpha import ALPHAS
from ditto_analytics.factors.fundamental import FUNDAMENTALS
from ditto_analytics.factors.primitives import PRIMITIVES
from ditto_analytics.factors.spec import FactorSpec
from ditto_analytics.factors.technical import TECHNICALS

__all__ = ["ALL_FACTOR_SPECS"]

ALL_FACTOR_SPECS: dict[str, FactorSpec] = {
    **PRIMITIVES,
    **TECHNICALS,
    **FUNDAMENTALS,
    **ALPHAS,
}
