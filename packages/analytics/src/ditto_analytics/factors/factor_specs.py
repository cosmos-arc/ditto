"""因子规格聚合注册表."""

from __future__ import annotations

from ditto_analytics.factors.alpha import ALPHAS
from ditto_analytics.factors.alternative import ALTERNATIVES
from ditto_analytics.factors.fundamental import FUNDAMENTALS
from ditto_analytics.factors.growth import GROWTHS
from ditto_analytics.factors.liquidity import LIQUIDITIES
from ditto_analytics.factors.momentum import MOMENTUMS
from ditto_analytics.factors.primitives import PRIMITIVES
from ditto_analytics.factors.quality import QUALITIES
from ditto_analytics.factors.size import SIZES
from ditto_analytics.factors.spec import FactorSpec
from ditto_analytics.factors.technical import TECHNICALS
from ditto_analytics.factors.value import VALUES
from ditto_analytics.factors.volatility import VOLATILITIES

__all__ = ["ALL_FACTOR_SPECS"]

ALL_FACTOR_SPECS: dict[str, FactorSpec] = {
    **PRIMITIVES,
    **TECHNICALS,
    **FUNDAMENTALS,
    **ALPHAS,
    **SIZES,
    **VALUES,
    **MOMENTUMS,
    **QUALITIES,
    **VOLATILITIES,
    **LIQUIDITIES,
    **GROWTHS,
    **ALTERNATIVES,
}
