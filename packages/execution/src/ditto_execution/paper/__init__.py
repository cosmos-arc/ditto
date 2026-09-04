"""Formal paper-trading contracts, reality rules, and persistence ports."""

from ditto_execution.paper.contracts import (
    FillAssumption,
    MarketSnapshotLineage,
    PaperFill,
    PaperOrder,
    PaperRealityContext,
    PaperRealityResult,
    PaperRealityStatus,
)
from ditto_execution.paper.reality import ASharePaperReality

__all__ = [
    "ASharePaperReality",
    "FillAssumption",
    "MarketSnapshotLineage",
    "PaperFill",
    "PaperOrder",
    "PaperRealityContext",
    "PaperRealityResult",
    "PaperRealityStatus",
]
