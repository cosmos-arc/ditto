"""
Factor and feature spec registry.

Canonical definitions live in ditto_features.factors.
This package provides the registry of all factor/feature definitions
used by the Ditto quantitative engine.
"""

from __future__ import annotations

from ditto_features.factors.alpha import ALPHAS
from ditto_features.factors.alternative import ALTERNATIVES
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.fundamental import FUNDAMENTALS
from ditto_features.factors.growth import GROWTHS
from ditto_features.factors.liquidity import LIQUIDITIES
from ditto_features.factors.momentum import MOMENTUMS
from ditto_features.factors.primitives import PRIMITIVES
from ditto_features.factors.production_guard import (
    UnsafeProductionFactorExpressionError,
    validate_production_factor_expression,
)
from ditto_features.factors.quality import QUALITIES
from ditto_features.factors.size import SIZES
from ditto_features.factors.spec import FactorContext, FactorSpec
from ditto_features.factors.technical import TECHNICALS
from ditto_features.factors.validate import validate_factor_specs
from ditto_features.factors.value import VALUES
from ditto_features.factors.volatility import VOLATILITIES

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
    "UnsafeProductionFactorExpressionError",
    "validate_factor_specs",
    "validate_production_factor_expression",
]
