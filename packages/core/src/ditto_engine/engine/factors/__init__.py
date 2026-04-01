"""
Factor and feature spec registry.

This package provides the canonical registry of all factor/feature
definitions used by the Ditto quantitative engine.
"""

from __future__ import annotations

from ditto_engine.engine.factors.alpha import ALPHAS
from ditto_engine.engine.factors.fundamental import FUNDAMENTALS
from ditto_engine.engine.factors.primitives import PRIMITIVES
from ditto_engine.engine.factors.spec import FactorContext, FactorSpec
from ditto_engine.engine.factors.technical import TECHNICALS

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
