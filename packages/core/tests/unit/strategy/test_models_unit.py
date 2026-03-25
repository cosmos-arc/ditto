"""Tests for StrategyRun / StrategyTemplate / StrategyVersion."""

from dataclasses import FrozenInstanceError

import pytest


class TestStrategyVersion:
    def test_create_version(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="etf_momentum_rotation",
            spec_json={"name": "v1 spec"},
            created_at="2026-01-15T10:00:00Z",
            status="draft",
        )
        assert ver.version == 1
        assert ver.status == "draft"

    def test_published_version(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="etf_momentum_rotation",
            spec_json={"name": "v1 spec"},
            created_at="2026-01-15T10:00:00Z",
            status="published",
        )
        assert ver.status == "published"

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import StrategyVersion

        ver = StrategyVersion(
            version=1,
            strategy_id="test",
            spec_json={},
            created_at="2026-01-15T10:00:00Z",
        )
        with pytest.raises(FrozenInstanceError):
            ver.version = 2  # type: ignore[misc]


class TestStrategyTemplate:
    def test_create_template(self) -> None:
        from ditto_core.strategy.models import StrategyTemplate

        tpl = StrategyTemplate(
            template_id="etf_rotation",
            name="ETF Rotation",
            description="ETF 轮动策略模板",
            asset_class="etf",
            required_signals=("momentum", "volatility"),
            built_in_constraints=("max_weight_per_instrument", "max_turnover"),
        )
        assert tpl.template_id == "etf_rotation"
        assert tpl.required_signals == ("momentum", "volatility")


class TestStrategyRun:
    def test_create_run(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-20260115-001",
            strategy_id="etf_momentum_rotation",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
            status="pending",
            parameters={"lookback": 252},
            baseline_run_id=None,
        )
        assert run.run_id == "RUN-20260115-001"
        assert run.status == "pending"
        assert run.parameters["lookback"] == 252

    def test_create_with_baseline(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-20260115-002",
            strategy_id="etf_momentum_rotation",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
            status="completed",
            parameters={"lookback": 126},
            baseline_run_id="RUN-20260115-001",
        )
        assert run.baseline_run_id == "RUN-20260115-001"

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import StrategyRun

        run = StrategyRun(
            run_id="RUN-001",
            strategy_id="test",
            spec_version=1,
            start="2025-01-01",
            end="2025-12-31",
        )
        with pytest.raises(FrozenInstanceError):
            run.status = "completed"  # type: ignore[misc]


class TestSignalSnapshot:
    def test_create_signal_snapshot(self) -> None:
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            signals={
                1: 0.85,
                2: 0.62,
                3: 0.41,
            },
        )
        assert snapshot.trade_date == "2026-01-15"
        assert len(snapshot.signals) == 3
        assert snapshot.signals[1] == pytest.approx(0.85)

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            signals={10: 0.5},
        )
        with pytest.raises(FrozenInstanceError):
            snapshot.trade_date = "2026-01-16"  # type: ignore[misc]

    def test_valid_until_default_none(self) -> None:
        """默认 valid_until 为 None（仅当日有效）。"""
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
        )
        assert snapshot.valid_until is None

    def test_valid_until_explicit(self) -> None:
        """显式设置 valid_until。"""
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            valid_until="2026-01-20",
        )
        assert snapshot.valid_until == "2026-01-20"


class TestTargetPortfolio:
    def test_create_target_portfolio(self) -> None:
        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            positions={
                1: 0.35,
                2: 0.35,
                3: 0.30,
            },
            cash_target=0.0,
        )
        assert target.cash_target == 0.0
        assert sum(target.positions.values()) == pytest.approx(1.0)

    def test_with_cash_reserve(self) -> None:
        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            positions={10: 0.40, 20: 0.40},
            cash_target=0.20,
        )
        assert target.cash_target == 0.20


class TestRebalancePlan:
    def test_create_rebalance_plan(self) -> None:
        from ditto_core.strategy.models import RebalancePlan

        plan = RebalancePlan(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            target_weights={
                1: 0.40,
                2: 0.35,
                3: 0.25,
            },
        )
        assert plan.executed is False
        assert plan.execution_date is None
        assert len(plan.target_weights) == 3

    def test_rebalance_plan_default_weights(self) -> None:
        from ditto_core.strategy.models import RebalancePlan

        plan = RebalancePlan(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
        )
        assert plan.target_weights == {}

    def test_rebalance_plan_executed(self) -> None:
        from ditto_core.strategy.models import RebalancePlan

        plan = RebalancePlan(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            executed=True,
            execution_date="2026-01-16",
        )
        assert plan.executed is True
        assert plan.execution_date == "2026-01-16"

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import RebalancePlan

        plan = RebalancePlan(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
        )
        with pytest.raises(FrozenInstanceError):
            plan.executed = True  # type: ignore[misc]
