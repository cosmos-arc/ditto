"""StrategyServiceFactory 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ditto_app.builders.strategy import (
    BacktestRuntimeBuilder,
    PublishedBacktestRuntime,
    StrategyServiceFactory,
)
from ditto_app.process.strategy import (
    BacktestService,
    BacktestServiceConfig,
    MarketServiceDataFeed,
    RunLifecycleService,
)
from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import SimpleFeeModel
from ditto_engine.risk.pre_trade import CompositePreTradeCheck
from ditto_kernel.identity import InstrumentId


def _make_runtime() -> PublishedBacktestRuntime:
    spec = StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", "etf"),
    )
    return PublishedBacktestRuntime(
        record=StrategySpecRecord(
            strategy_id=spec.strategy_id,
            name=spec.name,
            spec_json={},
            version=4,
            status="published",
            tags=spec.tags,
        ),
        spec=spec,
        pipeline=MagicMock(spec=StrategyPipeline),
        planner=SimpleExecutionPlanner(),
        brokerage=MagicMock(spec=BacktestBrokerage),
        pre_trade_check=MagicMock(spec=CompositePreTradeCheck),
        data_feed=MagicMock(spec=MarketServiceDataFeed),
        fee_model=SimpleFeeModel(),
        config=BacktestServiceConfig(
            strategy_id=spec.strategy_id,
            strategy_version="4",
            start_date="2026-01-01",
            end_date="2026-03-01",
            initial_cash=1_000_000.0,
            benchmark_id=InstrumentId(3_000_001),
        ),
    )


class TestStrategyServiceFactory:
    """Port strategy factory 的 catalog-backed backtest 测试。"""

    def test_build_backtest_service_from_catalog_uses_runtime_builder(self) -> None:
        """factory 应使用 BacktestRuntimeBuilder 组装 BacktestService。"""
        runtime = _make_runtime()
        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
        )

        assert isinstance(service, BacktestService)
        assert service._config.strategy_version == "4"
        assert service._pipeline is runtime.pipeline
        assert service._planner is runtime.planner
        assert service._brokerage is runtime.brokerage
        assert service._pre_trade_check is runtime.pre_trade_check
        assert service._data_feed is runtime.data_feed
        assert service._options.fee_model is runtime.fee_model
        runtime_builder.build_published_runtime.assert_called_once_with(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
            source="tushare",
        )

    def test_build_backtest_options_preserves_display_map(self) -> None:
        """_build_backtest_options 保留调用方传入的 display_map。"""
        from ditto_app.process.strategy import (
            BacktestServiceOptions,
        )

        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
        )
        display_map = {InstrumentId(1): "510300.SH"}
        options = BacktestServiceOptions(display_map=display_map)
        result = factory._build_backtest_options(options)
        assert result.display_map is display_map

    def test_build_backtest_service_from_catalog_injects_display_map(self) -> None:
        """catalog-backed 路径自动从 runtime.data_feed 注入 display_map。"""
        from dataclasses import replace

        test_display_map = {InstrumentId(1): "510300.SH"}
        mock_data_feed = MagicMock(spec=MarketServiceDataFeed)
        mock_data_feed.display_map = test_display_map

        runtime = _make_runtime()
        runtime = replace(runtime, data_feed=mock_data_feed)

        runtime_builder = MagicMock(spec=BacktestRuntimeBuilder)
        runtime_builder.build_published_runtime.return_value = runtime
        factory = StrategyServiceFactory(
            audit_service=MagicMock(spec=ExecutionAuditService),
            artifact_service=MagicMock(spec=StrategyArtifactService),
            run_service=MagicMock(spec=RunLifecycleService),
            backtest_runtime_builder=runtime_builder,
        )

        service = factory.build_backtest_service_from_catalog(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-01",
                end_date="2026-03-01",
                initial_cash=1_000_000.0,
            ),
            version=4,
        )

        assert service._options.display_map == test_display_map
