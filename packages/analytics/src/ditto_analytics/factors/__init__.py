"""
Factor and feature spec registry.

Canonical definitions live in ditto_analytics.factors.
This package provides the registry of all factor/feature definitions
used by the Ditto quantitative engine.
"""

from __future__ import annotations

from ditto_analytics.factors.alpha import ALPHAS
from ditto_analytics.factors.alternative import ALTERNATIVES
from ditto_analytics.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_analytics.factors.fundamental import FUNDAMENTALS
from ditto_analytics.factors.growth import GROWTHS
from ditto_analytics.factors.liquidity import LIQUIDITIES
from ditto_analytics.factors.momentum import MOMENTUMS
from ditto_analytics.factors.primitives import PRIMITIVES
from ditto_analytics.factors.quality import QUALITIES
from ditto_analytics.factors.size import SIZES
from ditto_analytics.factors.spec import FactorContext, FactorSpec
from ditto_analytics.factors.technical import TECHNICALS
from ditto_analytics.factors.validate import validate_factor_specs
from ditto_analytics.factors.value import VALUES
from ditto_analytics.factors.volatility import VOLATILITIES

__all__ = [
    "ALL_FACTOR_SPECS",
    "ALPHAS",
    "ALTERNATIVES",
    "FUNDAMENTALS",
    "GROWTHS",
    "LIQUIDITIES",
    "MOMENTUMS",
    "PRIMITIVES",
    "QUALITIES",
    "SIZES",
    "TECHNICALS",
    "VALUES",
    "VOLATILITIES",
    "FactorContext",
    "FactorSpec",
    "validate_factor_specs",
]
