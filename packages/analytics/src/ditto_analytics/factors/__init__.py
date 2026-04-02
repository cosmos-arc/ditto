"""
Factor and feature spec registry.

Canonical definitions live in ditto_analytics.factors.
This package provides the registry of all factor/feature definitions
used by the Ditto quantitative engine.
"""

from __future__ import annotations

from ditto_analytics.factors.alpha import ALPHAS
from ditto_analytics.factors.fundamental import FUNDAMENTALS
from ditto_analytics.factors.primitives import PRIMITIVES
from ditto_analytics.factors.spec import FactorContext, FactorSpec
from ditto_analytics.factors.technical import TECHNICALS

__all__ = [
    "ALL_FACTOR_SPECS",
    "ALPHAS",
    "FUNDAMENTALS",
    "PRIMITIVES",
    "TECHNICALS",
    "FactorContext",
    "FactorSpec",
]

ALL_FACTOR_SPECS: dict[str, FactorSpec] = {
    **PRIMITIVES,
    **TECHNICALS,
    **FUNDAMENTALS,
    **ALPHAS,
}
