"""Read-only portfolio exposure, constraint, and shock scenario preview."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

__all__ = [
    "PortfolioScenarioInput",
    "ScenarioExposure",
    "ScenarioPosition",
    "ScenarioPreview",
    "preview_portfolio_scenario",
]


def _empty_shocks() -> dict[str, float]:
    return {}


@dataclass(frozen=True)
class ScenarioPosition:
    """One deterministic position weight and optional industry classification."""

    instrument_id: int
    weight: float
    industry: str | None = None


@dataclass(frozen=True)
class PortfolioScenarioInput:
    """Exact current/proposed weights plus user-selected constraints and shocks."""

    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    current_positions: tuple[ScenarioPosition, ...]
    proposed_positions: tuple[ScenarioPosition, ...]
    cash_reserve_weight: float
    max_position_weight: float
    market_shock: float = 0.0
    industry_shocks: Mapping[str, float] = field(default_factory=_empty_shocks)


@dataclass(frozen=True)
class ScenarioExposure:
    """Exposure and deterministic shock return for one side of a preview."""

    gross_exposure: float
    cash_weight: float
    industry_exposure: Mapping[str, float]
    stressed_return: float


@dataclass(frozen=True)
class ScenarioPreview:
    """Read-only before/after risk facts; it is never an account mutation."""

    as_of: str
    valuation_snapshot_id: str
    source_snapshot_ids: tuple[str, ...]
    before: ScenarioExposure
    after: ScenarioExposure
    turnover: float
    constraint_findings: tuple[str, ...]


def _validate_positions(
    positions: tuple[ScenarioPosition, ...],
    *,
    label: str,
) -> None:
    seen: set[int] = set()
    for item in positions:
        if item.instrument_id <= 0 or item.instrument_id in seen:
            raise ValueError(f"{label} instrument identity is invalid")
        seen.add(item.instrument_id)
        if not math.isfinite(item.weight) or item.weight < 0.0:
            raise ValueError(f"{label} weight must be finite and non-negative")
        if item.industry is not None and not item.industry.strip():
            raise ValueError(f"{label} industry must be non-empty when provided")
    if sum(item.weight for item in positions) > 1.0 + 1e-9:
        raise ValueError(f"{label} weights exceed one")


def _exposure(
    positions: tuple[ScenarioPosition, ...],
    *,
    market_shock: float,
    industry_shocks: Mapping[str, float],
) -> ScenarioExposure:
    gross = sum(item.weight for item in positions)
    industries: dict[str, float] = {}
    stressed = 0.0
    for item in positions:
        industry = item.industry or "unclassified"
        industries[industry] = industries.get(industry, 0.0) + item.weight
        stressed += item.weight * (market_shock + industry_shocks.get(industry, 0.0))
    return ScenarioExposure(
        gross_exposure=round(gross, 12),
        cash_weight=round(max(0.0, 1.0 - gross), 12),
        industry_exposure=dict(sorted(industries.items())),
        stressed_return=round(stressed, 12),
    )


def preview_portfolio_scenario(value: PortfolioScenarioInput) -> ScenarioPreview:
    """Compute deterministic risk changes without reading or writing persistence."""
    if not value.as_of or not value.valuation_snapshot_id:
        raise ValueError("scenario requires exact as_of and valuation snapshot")
    if not value.source_snapshot_ids or len(set(value.source_snapshot_ids)) != len(
        value.source_snapshot_ids
    ):
        raise ValueError("scenario requires unique source snapshot IDs")
    if (
        not math.isfinite(value.cash_reserve_weight)
        or not 0.0 <= value.cash_reserve_weight < 1.0
        or not math.isfinite(value.max_position_weight)
        or not 0.0 < value.max_position_weight <= 1.0
    ):
        raise ValueError("scenario weight constraints are invalid")
    if not math.isfinite(value.market_shock):
        raise ValueError("market_shock must be finite")
    if not all(
        name.strip() and math.isfinite(shock)
        for name, shock in value.industry_shocks.items()
    ):
        raise ValueError("industry shocks must be named and finite")
    _validate_positions(value.current_positions, label="current")
    _validate_positions(value.proposed_positions, label="proposed")
    before = _exposure(
        value.current_positions,
        market_shock=value.market_shock,
        industry_shocks=value.industry_shocks,
    )
    after = _exposure(
        value.proposed_positions,
        market_shock=value.market_shock,
        industry_shocks=value.industry_shocks,
    )
    current = {item.instrument_id: item.weight for item in value.current_positions}
    proposed = {item.instrument_id: item.weight for item in value.proposed_positions}
    turnover = (
        sum(
            abs(proposed.get(item, 0.0) - current.get(item, 0.0))
            for item in set(current) | set(proposed)
        )
        / 2.0
    )
    findings = tuple(
        f"MAX_POSITION_WEIGHT:{item.instrument_id}"
        for item in sorted(
            value.proposed_positions, key=lambda position: position.instrument_id
        )
        if item.weight > value.max_position_weight + 1e-12
    )
    invested_limit = 1.0 - value.cash_reserve_weight
    if after.gross_exposure > invested_limit + 1e-9:
        findings = (*findings, "CASH_RESERVE_WEIGHT")
    return ScenarioPreview(
        as_of=value.as_of,
        valuation_snapshot_id=value.valuation_snapshot_id,
        source_snapshot_ids=value.source_snapshot_ids,
        before=before,
        after=after,
        turnover=round(turnover, 12),
        constraint_findings=findings,
    )
