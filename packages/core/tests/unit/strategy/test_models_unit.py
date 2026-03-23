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
                "159915.SZ": 0.85,
                "510300.SH": 0.62,
                "159949.SZ": 0.41,
            },
        )
        assert snapshot.trade_date == "2026-01-15"
        assert len(snapshot.signals) == 3
        assert snapshot.signals["159915.SZ"] == pytest.approx(0.85)

    def test_is_frozen(self) -> None:
        from ditto_core.strategy.models import SignalSnapshot

        snapshot = SignalSnapshot(
            trade_date="2026-01-15",
            strategy_id="test",
            run_id="RUN-001",
            signals={"A": 0.5},
        )
        with pytest.raises(FrozenInstanceError):
            snapshot.trade_date = "2026-01-16"  # type: ignore[misc]


class TestTargetPortfolio:
    def test_create_target_portfolio(self) -> None:
        from ditto_core.strategy.models import TargetPortfolio

        target = TargetPortfolio(
            trade_date="2026-01-15",
            strategy_id="etf_momentum_rotation",
            run_id="RUN-001",
            positions={
                "159915.SZ": 0.35,
                "510300.SH": 0.35,
                "159949.SZ": 0.30,
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
            positions={"A": 0.40, "B": 0.40},
            cash_target=0.20,
        )
        assert target.cash_target == 0.20
