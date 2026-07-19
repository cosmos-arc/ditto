"""FactorSpec-only registry with no governed-catalog import cycle."""

from __future__ import annotations

from ditto_features.factors.alpha import ALPHAS
from ditto_features.factors.alternative import ALTERNATIVES
from ditto_features.factors.fundamental import FUNDAMENTALS
from ditto_features.factors.growth import GROWTHS
from ditto_features.factors.liquidity import LIQUIDITIES
from ditto_features.factors.momentum import MOMENTUMS
from ditto_features.factors.primitives import PRIMITIVES
from ditto_features.factors.quality import QUALITIES
from ditto_features.factors.size import SIZES
from ditto_features.factors.spec import FactorSpec
from ditto_features.factors.technical import TECHNICALS
from ditto_features.factors.value import VALUES
from ditto_features.factors.volatility import VOLATILITIES

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
