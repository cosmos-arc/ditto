"""Portfolio construction step fail-closed behavior tests."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_backtest.portfolio_construction import (
    PortfolioConstructionContext,
    PortfolioConstructionOutcome,
)
from ditto_backtest.steps.portfolio_construction import PortfolioConstructionStep
from ditto_backtest.steps.types import StepContext
from ditto_kernel.identity import InstrumentId
from packages.backtest.tests.unit._helpers import _make_account_view, _make_ctx


@dataclass(frozen=True)
class _Target:
    positions: dict[InstrumentId, float]


class _FailingConstructor:
    def construct(
        self,
        context: PortfolioConstructionContext,
    ) -> PortfolioConstructionOutcome:
        return PortfolioConstructionOutcome.failed(
            code="insufficient_history",
            message=f"no PIT window for {context.trade_date}",
            evidence={
                "knowledge_cutoff": context.knowledge_cutoff.isoformat(),
                "publication_cutoff": context.publication_cutoff.isoformat(),
                "snapshot_ids": context.source_snapshot_ids,
            },
        )


class _SuccessfulConstructor:
    def construct(
        self,
        context: PortfolioConstructionContext,
    ) -> PortfolioConstructionOutcome:
        return PortfolioConstructionOutcome.completed(
            target_portfolio=_Target({1: 0.25, 2: 0.75}),
            evidence={"policy_digest": "digest-1"},
        )


def _ready_context() -> StepContext:
    ctx = _make_ctx(trade_date="2026-01-15", is_rebalance_day=True)
    ctx.account_view = _make_account_view()
    ctx.target_portfolio = _Target({1: 0.5, 2: 0.5})
    ctx.source_snapshot_ids = {1: "snap-b", 2: "snap-a"}
    return ctx


def test_failed_construction_clears_target_and_stops_step_chain() -> None:
    ctx = _ready_context()

    result = PortfolioConstructionStep(_FailingConstructor()).execute(ctx)

    assert result.success is False
    assert result.errors == ("insufficient_history: no PIT window for 2026-01-15",)
    assert ctx.target_portfolio is None
    assert ctx.portfolio_construction_evidence == {
        "knowledge_cutoff": "2026-01-14T00:00:00",
        "publication_cutoff": "2026-01-14T00:00:00",
        "snapshot_ids": ("snap-a", "snap-b"),
    }
    assert ctx.portfolio_construction_failure == "insufficient_history"


def test_successful_construction_replaces_candidate_target() -> None:
    ctx = _ready_context()

    result = PortfolioConstructionStep(_SuccessfulConstructor()).execute(ctx)

    assert result.success is True
    assert ctx.require_target_portfolio().positions == {1: 0.25, 2: 0.75}
    assert ctx.portfolio_construction_evidence == {"policy_digest": "digest-1"}
    assert ctx.portfolio_construction_failure is None


def test_missing_constructor_preserves_legacy_target() -> None:
    ctx = _ready_context()
    original = ctx.target_portfolio

    result = PortfolioConstructionStep(None).execute(ctx)

    assert result.success is True
    assert ctx.target_portfolio is original
