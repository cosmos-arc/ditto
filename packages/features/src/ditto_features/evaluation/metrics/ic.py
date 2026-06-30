"""
IC (Information Coefficient) computation and analysis.

This module re-exports all public IC functions from the split sub-modules.
"""

from __future__ import annotations

from .ic_computation import (
    ic_autocorrelation,
    ic_decay,
    ic_summary,
    pearson_ic,
    rank_ic,
)
from .ic_report import (
    ic_momentum,
    regime_adjusted_ic,
    sub_period_ic,
)

__all__ = [
    "ic_autocorrelation",
    "ic_decay",
    "ic_momentum",
    "ic_summary",
    "pearson_ic",
    "rank_ic",
    "regime_adjusted_ic",
    "sub_period_ic",
]
