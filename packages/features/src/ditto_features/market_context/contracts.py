"""Feature-owned market-regime input and output contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

__all__ = [
    "MarketRegimeDriver",
    "MarketRegimeFeature",
    "MarketRegimeFeatureSet",
    "MarketRegimeInput",
    "MarketRegimeLabel",
]

type MarketContextStatus = Literal["ready", "degraded", "blocked"]
type MarketRegimeLabel = Literal["risk_on", "balanced", "risk_off"]


def _aware(field: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"market regime {field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MarketRegimeInput:
    """Normalized facts supplied by application without a features→data edge."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    advancing_count: int | None
    declining_count: int | None
    universe_count: int | None
    benchmark_return_20d: float | None
    small_cap_return_20d: float | None
    large_cap_return_20d: float | None
    realized_volatility_20d: float | None
    global_return_1d: float | None
    macro_surprise_score: float | None
    macro_trend_score: float | None
    declared_missing_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject ambiguous time, lineage, count, and numeric inputs."""
        for field in ("as_of", "knowledge_cutoff", "publication_cutoff"):
            _aware(field, getattr(self, field))
        if self.publication_cutoff > self.knowledge_cutoff:
            raise ValueError(
                "market regime publication_cutoff exceeds knowledge_cutoff"
            )
        if self.knowledge_cutoff > self.as_of:
            raise ValueError("market regime knowledge_cutoff exceeds as_of")
        if not self.source_snapshot_ids or len(set(self.source_snapshot_ids)) != len(
            self.source_snapshot_ids
        ):
            raise ValueError("market regime requires unique source_snapshot_ids")
        if any(
            not value or value.strip() != value
            for value in self.source_snapshot_ids + self.declared_missing_inputs
        ):
            raise ValueError(
                "market regime lineage and missing-input IDs must normalize"
            )
        counts = (self.advancing_count, self.declining_count, self.universe_count)
        if any(value is not None and value < 0 for value in counts):
            raise ValueError("market regime breadth counts must be non-negative")
        if (
            all(value is not None for value in counts)
            and self.advancing_count is not None
            and self.declining_count is not None
            and self.universe_count is not None
            and self.advancing_count + self.declining_count > self.universe_count
        ):
            raise ValueError("market regime breadth counts exceed universe_count")
        numeric_values = (
            self.benchmark_return_20d,
            self.small_cap_return_20d,
            self.large_cap_return_20d,
            self.realized_volatility_20d,
            self.global_return_1d,
            self.macro_surprise_score,
            self.macro_trend_score,
        )
        if any(
            value is not None and not math.isfinite(value) for value in numeric_values
        ):
            raise ValueError("market regime numeric inputs must be finite")


@dataclass(frozen=True, slots=True)
class MarketRegimeFeature:
    """One versioned normalized feature and its score contribution."""

    name: str
    category: str
    value: float
    weight: float
    contribution: float


@dataclass(frozen=True, slots=True)
class MarketRegimeDriver:
    """One ordered driver attribution for the regime conclusion."""

    name: str
    category: str
    contribution: float
    direction: Literal["supportive", "pressuring", "neutral"]


@dataclass(frozen=True, slots=True)
class MarketRegimeFeatureSet:
    """Deterministic, replayable market-regime result."""

    feature_set_id: str
    feature_version: str
    input_hash: str
    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    source_snapshot_ids: tuple[str, ...]
    status: MarketContextStatus
    label: MarketRegimeLabel | None
    score: float | None
    features: tuple[MarketRegimeFeature, ...]
    drivers: tuple[MarketRegimeDriver, ...]
    missing_inputs: tuple[str, ...]
