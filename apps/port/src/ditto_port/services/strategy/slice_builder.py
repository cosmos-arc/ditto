"""published strategy 到单日 Slice 的组装器。"""

from __future__ import annotations

from ditto_core.backtest.data_feed import Slice
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId

from ditto_port.services.strategy.market_data_feed import (
    MarketServiceDataFeed,
    MarketServiceDataFeedConfig,
)
from ditto_port.services.strategy.runtime_builder import StrategyRuntimeBuilder

__all__ = ["StrategySliceBuilder"]


class StrategySliceBuilder:
    """为 published strategy 组装 research/recommendation 所需单日 Slice。"""

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

    def build_published_slice(
        self,
        strategy_id: str,
        *,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> Slice:
        """从 published strategy catalog 构造指定日期的市场切片。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            strategy_id,
            version,
        )
        benchmark_id = self._resolve_benchmark(
            runtime.spec.benchmark,
            source,
            trade_date,
        )
        data_feed = MarketServiceDataFeed(
            metadata_service=self._metadata_service,
            market_service=self._market_service,
            config=MarketServiceDataFeedConfig(
                universe_id=runtime.spec.universe,
                asset_class=runtime.spec.asset_class,
                start_date=trade_date,
                end_date=trade_date,
                benchmark_id=benchmark_id,
                source=source,
            ),
        )
        if trade_date not in data_feed.trading_days():
            msg = f"trade_date 不在可用交易日内: {trade_date}"
            raise ValueError(msg)
        return data_feed.get_slice(trade_date)

    def _resolve_benchmark(
        self,
        benchmark: str | None,
        source: str,
        as_of: str,
    ) -> InstrumentId | None:
        """将 benchmark ticker 解析为 InstrumentId。"""
        if benchmark is None:
            return None
        iid = self._metadata_service.resolve_instrument_id(benchmark, source, as_of)
        return InstrumentId(iid) if iid is not None else None
