"""
Execution boundary types — decoupled from strategy module.

Defines the minimal interface that the execution planner requires
from a target portfolio, allowing execution to depend only on its
own boundary types rather than on ditto_engine.alpha.models.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ditto_kernel.identity import InstrumentId

__all__ = ["TargetPortfolioLike"]


@runtime_checkable
class TargetPortfolioLike(Protocol):
    """
    Minimal interface for a target portfolio consumed by ExecutionPlanner.

    ``ditto_engine.alpha.models.TargetPortfolio`` satisfies this protocol
    without any changes.
    """

    @property
    def positions(self) -> dict[InstrumentId, float]:
        """instrument_id → target weight mapping."""
        ...
