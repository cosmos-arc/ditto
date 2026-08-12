"""Portfolio construction step between strategy selection and planning."""

from __future__ import annotations

from ditto_kernel import traced

from ditto_backtest.portfolio_construction import (
    PortfolioConstructionContext,
    PortfolioConstructor,
)
from ditto_backtest.steps.types import StepContext, StepResult

__all__ = ["PortfolioConstructionStep"]


class PortfolioConstructionStep:
    """Apply an optional injected constructor without a legacy fallback."""

    def __init__(self, constructor: PortfolioConstructor | None) -> None:
        """Store the optional provider; ``None`` preserves legacy behavior."""
        self._constructor = constructor

    @traced("backtest.step.portfolio_construction")
    def execute(self, ctx: StepContext) -> StepResult:
        """Replace the candidate target or return an explicit failed step."""
        if not ctx.is_rebalance_day or self._constructor is None:
            return StepResult.skipped()
        outcome = self._constructor.construct(
            PortfolioConstructionContext(
                trade_date=ctx.time_context.trade_date,
                decision_time=ctx.time_context.decision_time,
                knowledge_cutoff=ctx.time_context.pit_cutoff,
                publication_cutoff=ctx.time_context.pit_cutoff,
                source_snapshot_ids=tuple(
                    sorted(set(ctx.source_snapshot_ids.values()))
                ),
                candidate_target=ctx.require_target_portfolio(),
                account_view=ctx.require_account_view(),
            )
        )
        ctx.portfolio_construction_evidence = dict(outcome.evidence)
        if not outcome.success:
            code = outcome.failure_code or "portfolio_construction_failed"
            message = outcome.failure_message or "unknown failure"
            ctx.target_portfolio = None
            ctx.portfolio_construction_failure = code
            return StepResult.fail(f"{code}: {message}")
        if outcome.target_portfolio is None:
            ctx.target_portfolio = None
            ctx.portfolio_construction_failure = "missing_constructed_target"
            return StepResult.fail(
                "missing_constructed_target: successful outcome has no target"
            )
        ctx.target_portfolio = outcome.target_portfolio
        ctx.portfolio_construction_failure = None
        return StepResult.ok()
