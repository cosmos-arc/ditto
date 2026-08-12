"""Portfolio policy registry and runtime adapter contract tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.eod_coordinator import EodStrategyRequest
from ditto_application.processes.execution.strategy_run_process import (
    StrategyRunMode,
    StrategyRunResult,
)
from ditto_application.processes.portfolio.construction import (
    PortfolioConstructionDecision,
    PortfolioConstructionIdentity,
    PortfolioConstructionTemporalContext,
)
from ditto_application.processes.portfolio.runtime_adapters import (
    BacktestPortfolioConstructionAdapter,
    EodPortfolioConstructionAdapter,
    PortfolioPolicyBinding,
    VersionedPortfolioPolicyRegistry,
)
from ditto_backtest.portfolio_construction import PortfolioConstructionContext
from ditto_portfolio.rebalancing.optimization_models import (
    OptimizationMethod,
    PortfolioConstructionPolicy,
)
from ditto_strategy.alpha.models import TargetPortfolio
from packages.backtest.tests.unit._helpers import _make_account_view


def _policy() -> PortfolioConstructionPolicy:
    return PortfolioConstructionPolicy(
        policy_id="mvo-core",
        version=1,
        method=OptimizationMethod.MVO,
    )


def test_registry_resolves_exact_strategy_and_sleeve_only() -> None:
    registry = VersionedPortfolioPolicyRegistry(
        (
            PortfolioPolicyBinding(
                strategy_id="strategy-a",
                sleeve_id="core",
                policy=_policy(),
            ),
        )
    )

    assert (
        registry.resolve(
            PortfolioConstructionIdentity(
                account_id="account-1",
                sleeve_id="core",
                strategy_id="strategy-a",
                run_id="run-1",
                trade_date="2026-04-01",
            )
        )
        == _policy()
    )
    assert (
        registry.resolve(
            PortfolioConstructionIdentity(
                account_id="account-1",
                sleeve_id="satellite",
                strategy_id="strategy-a",
                run_id="run-1",
                trade_date="2026-04-01",
            )
        )
        is None
    )


def test_backtest_adapter_maps_explicit_temporal_context_and_failure() -> None:
    process = Mock()
    process.construct.return_value = PortfolioConstructionDecision(
        success=False,
        target=None,
        evidence={"policy_digest": "sha256:policy"},
        failure_code="infeasible",
        failure_message="constraints conflict",
    )
    candidate = TargetPortfolio(
        trade_date="2026-04-01",
        strategy_id="strategy-a",
        run_id="run-1",
        positions={1: 1.0},
        cash_target=0.0,
    )
    adapter = BacktestPortfolioConstructionAdapter(
        process=process,
        account_id="research-1",
        sleeve_id="core",
        strategy_id="strategy-a",
    )

    outcome = adapter.construct(
        PortfolioConstructionContext(
            trade_date="2026-04-01",
            decision_time=datetime(2026, 4, 1, 15),
            knowledge_cutoff=datetime(2026, 4, 1),
            publication_cutoff=datetime(2026, 3, 31, 20),
            source_snapshot_ids=("snap-1",),
            candidate_target=candidate,
            account_view=_make_account_view(),
        )
    )

    assert outcome.success is False
    assert outcome.failure_code == "infeasible"
    temporal = process.construct.call_args.kwargs["temporal"]
    assert temporal.publication_cutoff == datetime(2026, 3, 31, 20)


def test_eod_adapter_raises_stable_blocking_error_on_construction_failure() -> None:
    process = Mock()
    process.construct.return_value = PortfolioConstructionDecision(
        success=False,
        target=None,
        evidence={"policy_digest": "sha256:policy"},
        failure_code="infeasible",
        failure_message="constraints conflict",
    )
    adapter = EodPortfolioConstructionAdapter(
        process=process,
        account_id="paper-1",
        sleeve_id="core",
        temporal_context_for=lambda date, snapshots: (
            PortfolioConstructionTemporalContext(
                decision_time=datetime(2026, 4, 1, 15),
                knowledge_cutoff=datetime(2026, 4, 1),
                publication_cutoff=datetime(2026, 3, 31, 20),
                source_snapshot_ids=tuple(sorted(snapshots.values())),
            )
        ),
    )
    target = TargetPortfolio(
        trade_date="2026-04-01",
        strategy_id="strategy-a",
        run_id="run-1",
        positions={1: 1.0},
    )
    result = StrategyRunResult(
        run_id="run-1",
        trade_date="2026-04-01",
        strategy_id="strategy-a",
        target=target,
        mode=StrategyRunMode.RECOMMENDATION,
    )

    with pytest.raises(AppProcessError) as error:
        adapter(
            result,
            EodStrategyRequest("strategy-a", "1", ("stock_daily",)),
            "2026-04-01",
            {"stock_daily": "snap-1"},
        )

    assert error.value.details["code"] == "PORTFOLIO_CONSTRUCTION_BLOCKED"
    assert error.value.details["failure_code"] == "infeasible"
