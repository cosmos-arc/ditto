"""Read-only application orchestration for deterministic portfolio scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from ditto_portfolio.portfolio_comparison import (
    NormalizedPortfolio,
    PortfolioComparisonError,
    constrained_target_weights,
)
from ditto_risk.portfolio_scenario import (
    PortfolioScenarioInput,
    ScenarioPosition,
    ScenarioPreview,
    preview_portfolio_scenario,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.portfolio_comparison import (
    PortfolioComparisonQueryPort,
    PortfolioComparisonRequest,
)

__all__ = [
    "PortfolioScenarioPreviewPort",
    "PortfolioScenarioPreviewView",
    "PortfolioScenarioRequest",
    "PreviewPortfolioScenarioQuery",
]

type ScenarioBaselineKind = Literal["model", "paper", "manual"]


@dataclass(frozen=True, kw_only=True)
class PortfolioScenarioRequest:
    """User constraints and shocks; it contains no model-generated target weights."""

    comparison: PortfolioComparisonRequest
    baseline_kind: ScenarioBaselineKind
    excluded_instrument_ids: frozenset[int]
    max_position_weight: Decimal
    cash_reserve_weight: Decimal
    market_shock: float = 0.0
    industry_shocks: Mapping[str, float] | None = None


@dataclass(frozen=True, kw_only=True)
class PortfolioScenarioPreviewView:
    """Deterministic proposed weights and risk changes with no side effects."""

    baseline_kind: ScenarioBaselineKind
    proposed_weights: Mapping[int, Decimal]
    risk: ScenarioPreview
    applied_constraints: tuple[str, ...]


@runtime_checkable
class PortfolioScenarioPreviewPort(Protocol):
    """Agent/apps-facing preview-only leaf contract."""

    def preview(
        self,
        request: PortfolioScenarioRequest,
    ) -> PortfolioScenarioPreviewView:
        """Compute a proposal and never persist it."""
        ...


def _positions(
    portfolio: NormalizedPortfolio,
    weights: Mapping[int, Decimal] | None = None,
) -> tuple[ScenarioPosition, ...]:
    industries = {item.instrument_id: item.industry for item in portfolio.positions}
    resolved = weights or {
        item.instrument_id: item.weight for item in portfolio.positions
    }
    return tuple(
        ScenarioPosition(
            instrument_id=instrument_id,
            weight=float(weight),
            industry=industries.get(instrument_id),
        )
        for instrument_id, weight in sorted(resolved.items())
    )


class PreviewPortfolioScenarioQuery:
    """Compose comparison facts with portfolio constraints and risk calculations."""

    def __init__(self, *, comparison: PortfolioComparisonQueryPort) -> None:
        self._comparison = comparison

    def preview(
        self,
        request: PortfolioScenarioRequest,
    ) -> PortfolioScenarioPreviewView:
        """Return a read-only proposal computed entirely by deterministic services."""
        comparison = self._comparison.get(request.comparison)
        baseline = getattr(comparison, request.baseline_kind)
        baseline_weights = {
            item.instrument_id: item.weight for item in baseline.positions
        }
        try:
            proposed = constrained_target_weights(
                baseline_weights,
                excluded_instrument_ids=request.excluded_instrument_ids,
                max_position_weight=request.max_position_weight,
                cash_reserve_weight=request.cash_reserve_weight,
            )
            risk = preview_portfolio_scenario(
                PortfolioScenarioInput(
                    as_of=comparison.as_of,
                    valuation_snapshot_id=comparison.valuation_snapshot_id,
                    source_snapshot_ids=comparison.source_snapshot_ids,
                    current_positions=_positions(baseline),
                    proposed_positions=_positions(baseline, proposed),
                    cash_reserve_weight=float(request.cash_reserve_weight),
                    max_position_weight=float(request.max_position_weight),
                    market_shock=request.market_shock,
                    industry_shocks=request.industry_shocks or {},
                )
            )
        except (PortfolioComparisonError, ValueError) as exc:
            raise AppQueryError(
                f"portfolio scenario failed closed: {exc}",
                code="PORTFOLIO_SCENARIO_INVALID",
                reason=str(exc),
            ) from exc
        constraints = (
            f"cash_reserve_weight={request.cash_reserve_weight}",
            f"max_position_weight={request.max_position_weight}",
            *(
                f"excluded_instrument_id={item}"
                for item in sorted(request.excluded_instrument_ids)
            ),
        )
        return PortfolioScenarioPreviewView(
            baseline_kind=request.baseline_kind,
            proposed_weights=proposed,
            risk=risk,
            applied_constraints=constraints,
        )
