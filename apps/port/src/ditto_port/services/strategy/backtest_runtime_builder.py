"""published strategy 到 backtest runtime 的装配器。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_core.accounting.account import Account
from ditto_core.accounting.cash import CashBook
from ditto_core.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_core.execution.brokerage import BacktestBrokerage
from ditto_core.execution.planner import SimpleExecutionPlanner
from ditto_core.execution.reality import BrokerageModel, FeeModel, SimpleFeeModel
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_core.strategy.specs import StrategySpec
from ditto_datahub.models.strategy import StrategySpecRecord
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId

from ditto_port.services.strategy.backtest_service import BacktestServiceConfig
from ditto_port.services.strategy.market_data_feed import (
    MarketServiceDataFeed,
    MarketServiceDataFeedConfig,
)
from ditto_port.services.strategy.runtime_builder import (
    StrategyRuntimeBuilder,
)

__all__ = ["BacktestRuntimeBuilder", "PublishedBacktestRuntime"]


@dataclass(frozen=True)
class PublishedBacktestRuntime:
    """从 published strategy 派生出的完整回测运行时。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline
    planner: SimpleExecutionPlanner
    brokerage: BacktestBrokerage
    pre_trade_check: CompositePreTradeCheck
    data_feed: MarketServiceDataFeed
    fee_model: FeeModel
    config: BacktestServiceConfig


class BacktestRuntimeBuilder:
    """为 published strategy 组装最小可运行回测依赖。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        market_service: MarketService,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._market_service = market_service

    def build_published_runtime(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        source: str = "tushare",
    ) -> PublishedBacktestRuntime:
        """从 published strategy catalog 构造回测运行时。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            config.strategy_id,
            version,
        )
        fee_model = SimpleFeeModel()
        brokerage = BacktestBrokerage(
            account=Account(
                cash=CashBook(
                    available=config.initial_cash,
                    settled=config.initial_cash,
                    frozen=0.0,
                )
            ),
            model=BrokerageModel(fee_model=fee_model),
        )
        benchmark_id = self._resolve_benchmark(
            config.benchmark_id,
            runtime.spec.benchmark,
            source,
            config.start_date,
        )
        resolved_config = replace(
            config,
            strategy_version=str(runtime.record.version),
            benchmark_id=benchmark_id,
        )
        return PublishedBacktestRuntime(
            record=runtime.record,
            spec=runtime.spec,
            pipeline=runtime.pipeline,
            planner=SimpleExecutionPlanner(),
            brokerage=brokerage,
            pre_trade_check=CompositePreTradeCheck(
                checks=(LotSizeCheck(), BuyingPowerCheck()),
            ),
            data_feed=MarketServiceDataFeed(
                metadata_service=self._metadata_service,
                market_service=self._market_service,
                config=MarketServiceDataFeedConfig(
                    universe_id=runtime.spec.universe,
                    asset_class=runtime.spec.asset_class,
                    start_date=config.start_date,
                    end_date=config.end_date,
                    benchmark_id=resolved_config.benchmark_id,
                    source=source,
                ),
            ),
            fee_model=fee_model,
            config=resolved_config,
        )

    def _resolve_benchmark(
        self,
        config_benchmark: InstrumentId | None,
        spec_benchmark: str | None,
        source: str,
        as_of: str,
    ) -> InstrumentId | None:
        """解析 benchmark：优先使用 config 中的 InstrumentId，否则从 spec 解析。"""
        if config_benchmark is not None:
            return config_benchmark
        if spec_benchmark is None:
            return None
        iid = self._metadata_service.resolve_instrument_id(
            spec_benchmark,
            source,
            as_of,
        )
        return InstrumentId(iid) if iid is not None else None
