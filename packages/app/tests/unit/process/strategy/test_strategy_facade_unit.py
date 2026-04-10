"""StrategyFacade 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.builders import StrategyServiceFactory, StrategySliceBuilder
from ditto_app.process.execution.backtest_process import BacktestServiceConfig
from ditto_app.process.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunResult,
    StrategyRunServiceConfig,
)
from ditto_engine.alpha.models import TargetPortfolio
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.statistics import BacktestReport


class TestStrategyFacade:
    """统一策略 facade 测试。"""

    def test_run_strategy_from_catalog_executes_built_service(self) -> None:
        """facade 应构造 catalog-backed StrategyRunService 并执行。"""
        run_service = MagicMock()
        run_service.run.return_value = StrategyRunResult(
            run_id="run-001",
            trade_date="2026-03-24",
            strategy_id="momentum-etf",
            target=TargetPortfolio(
                trade_date="2026-03-24",
                strategy_id="momentum-etf",
                run_id="run-001",
                positions={1: 0.5},
                cash_target=0.5,
            ),
            mode=StrategyRunMode.RESEARCH,
        )
        factory = MagicMock(spec=StrategyServiceFactory)
        factory.build_strategy_run_service_from_catalog.return_value = run_service
        facade = StrategyFacade(factory=factory)
        slice_ = MagicMock(spec=Slice)

        result = facade.run_strategy_from_catalog(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                mode=StrategyRunMode.RESEARCH,
            ),
            trade_date="2026-03-24",
            slice_=slice_,
            version=3,
        )

        assert result.run_id == "run-001"
        factory.build_strategy_run_service_from_catalog.assert_called_once()
        run_service.run.assert_called_once_with("2026-03-24", slice_)

    def test_run_backtest_from_catalog_executes_built_service(self) -> None:
        """facade 应构造 catalog-backed BacktestService 并执行。"""
        backtest_service = MagicMock()
        backtest_service.run.return_value = MagicMock(spec=BacktestReport)
        factory = MagicMock(spec=StrategyServiceFactory)
        factory.build_backtest_service_from_catalog.return_value = backtest_service
        facade = StrategyFacade(factory=factory)

        result = facade.run_backtest_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-24",
            ),
            version=2,
        )

        assert result is backtest_service.run.return_value
        factory.build_backtest_service_from_catalog.assert_called_once()
        backtest_service.run.assert_called_once_with()

    def test_run_strategy_for_date_from_catalog_builds_slice_before_execution(
        self,
    ) -> None:
        """facade 应先构造单日 Slice，再执行 catalog-backed StrategyRunService。"""
        run_service = MagicMock()
        run_service.run.return_value = MagicMock(spec=StrategyRunResult)
        factory = MagicMock(spec=StrategyServiceFactory)
        factory.build_strategy_run_service_from_catalog.return_value = run_service
        slice_builder = MagicMock(spec=StrategySliceBuilder)
        slice_ = MagicMock(spec=Slice)
        slice_builder.build_published_slice.return_value = slice_
        facade = StrategyFacade(factory=factory, slice_builder=slice_builder)

        result = facade.run_strategy_for_date_from_catalog(
            config=StrategyRunServiceConfig(
                strategy_id="momentum-etf",
                mode=StrategyRunMode.RECOMMENDATION,
            ),
            trade_date="2026-03-24",
            version=3,
        )

        assert result is run_service.run.return_value
        slice_builder.build_published_slice.assert_called_once_with(
            "momentum-etf",
            trade_date="2026-03-24",
            version=3,
            source="tushare",
        )
        run_service.run.assert_called_once_with("2026-03-24", slice_)
