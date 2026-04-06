"""BacktestRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from ditto_app.builders import (
    BacktestRuntimeBuilder,
    PublishedStrategyRuntime,
)
from ditto_app.process.backtest_service import BacktestServiceConfig
from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
from ditto_engine.backtest.data_feed import ProviderBackedDataFeed
from ditto_engine.execution.brokerage import BacktestBrokerage
from ditto_engine.execution.planner import SimpleExecutionPlanner
from ditto_engine.execution.reality import SimpleFeeModel
from ditto_engine.risk.pre_trade import CompositePreTradeCheck


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
        metadata_service.get_universe.return_value = [2_000_001, 2_000_002]
        metadata_service.get_instrument.return_value = {
            "ticker": "510300",
            "exchange": "XSHG",
        }
        data_provider = MagicMock(spec=DataProvider)
        builder = BacktestRuntimeBuilder(
            strategy_runtime_builder=strategy_runtime_builder,
            metadata_service=metadata_service,
            data_provider=data_provider,
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
        # data_feed 是 ProviderBackedDataFeed 实例
        assert isinstance(runtime.data_feed, ProviderBackedDataFeed)
        assert hasattr(runtime.data_feed, "trading_days")
        assert hasattr(runtime.data_feed, "get_slice")
        # display_map 是 dict[InstrumentId, str]
        assert isinstance(runtime.display_map, dict)
        assert isinstance(runtime.planner, SimpleExecutionPlanner)
        assert isinstance(runtime.brokerage, BacktestBrokerage)
        assert isinstance(runtime.pre_trade_check, CompositePreTradeCheck)
        assert isinstance(runtime.fee_model, SimpleFeeModel)
        assert runtime.brokerage.get_account().cash.available == 2_000_000.0
        strategy_runtime_builder.build_published_runtime.assert_called_once_with(
            "momentum-etf",
            2,
        )
