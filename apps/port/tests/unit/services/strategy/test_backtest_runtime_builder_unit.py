"""BacktestRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_core.backtest.risk.pre_trade import CompositePreTradeCheck
from ditto_core.execution.brokerage import BacktestBrokerage
from ditto_core.execution.planner import SimpleExecutionPlanner
from ditto_core.execution.reality import SimpleFeeModel
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_core.strategy.specs import StrategySpec
from ditto_datahub.models.strategy import StrategySpecRecord
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_port.services.strategy import (
    BacktestRuntimeBuilder,
    BacktestServiceConfig,
    MarketServiceDataFeed,
    PublishedStrategyRuntime,
)


def _make_strategy_spec() -> StrategySpec:
    """构造测试用 StrategySpec。"""
    return StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        benchmark="000300.SH",
        params={"top_k": 3},
        tags=("momentum", "etf"),
    )


class TestBacktestRuntimeBuilder:
    """published backtest runtime 装配测试。"""

    def test_build_published_runtime_creates_minimal_backtest_components(self) -> None:
        """builder 应从 published runtime 构造可跑的 backtest 依赖。"""
        spec = _make_strategy_spec()
        strategy_runtime_builder = MagicMock()
        strategy_runtime_builder.build_published_runtime.return_value = (
            PublishedStrategyRuntime(
                record=StrategySpecRecord(
                    strategy_id=spec.strategy_id,
                    name=spec.name,
                    spec_json=asdict(spec),
                    version=2,
                    status="published",
                    tags=spec.tags,
                ),
                spec=spec,
                pipeline=MagicMock(spec=StrategyPipeline),
            )
        )
        metadata_service = MagicMock(spec=MetadataService)
        metadata_service.resolve_instrument_id.return_value = 3_000_001
        market_service = MagicMock(spec=MarketService)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            market_service=market_service,
        )

        runtime = builder.build_published_runtime(
            config=BacktestServiceConfig(
                strategy_id="momentum-etf",
                start_date="2026-01-10",
                end_date="2026-01-13",
                initial_cash=2_000_000.0,
            ),
            version=2,
        )

        assert runtime.config.strategy_version == "2"
        assert runtime.config.benchmark_id == 3_000_001
        assert isinstance(runtime.data_feed, MarketServiceDataFeed)
        assert isinstance(runtime.planner, SimpleExecutionPlanner)
        assert isinstance(runtime.brokerage, BacktestBrokerage)
        assert isinstance(runtime.pre_trade_check, CompositePreTradeCheck)
        assert isinstance(runtime.fee_model, SimpleFeeModel)
        assert runtime.brokerage.get_account().cash.available == 2_000_000.0
        strategy_runtime_builder.build_published_runtime.assert_called_once_with(
            "momentum-etf",
            2,
        )
