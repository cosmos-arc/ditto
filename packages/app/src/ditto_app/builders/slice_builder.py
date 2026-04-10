"""published strategy 到单日 Slice 的组装器."""

from __future__ import annotations

from ditto_data.provider import DataProvider
from ditto_data.services.metadata_service import MetadataService
from ditto_engine.backtest.data_feed import ProviderBackedDataFeed, Slice

from ditto_app.builders._resolution import resolve_benchmark, resolve_instrument_display
from ditto_app.builders.runtime_builder import StrategyRuntimeBuilder

__all__ = [
    "StrategySliceBuilder",
]


class StrategySliceBuilder:
    """为 published strategy 组装 research/recommendation 所需单日 Slice。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        data_provider: DataProvider,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._data_provider = data_provider

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
        benchmark_id = resolve_benchmark(
            runtime.spec.benchmark,
            self._metadata_service,
            source,
            trade_date,
        )

        # 解析 universe → tickers + id_map
        universe_ids = self._metadata_service.get_universe(
            runtime.spec.universe,
            asof=trade_date,
        )
        resolution = resolve_instrument_display(universe_ids, self._metadata_service)
        tickers = resolution.tickers
        id_map = resolution.id_map

        data_feed = ProviderBackedDataFeed(
            self._data_provider,
            tickers=tickers,
            start_date=trade_date,
            end_date=trade_date,
            id_map=id_map,
            benchmark_id=benchmark_id,
        )
        if trade_date not in data_feed.trading_days():
            msg = f"trade_date 不在可用交易日内: {trade_date}"
            raise ValueError(msg)
        return data_feed.get_slice(trade_date)
