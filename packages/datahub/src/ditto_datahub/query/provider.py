"""
DataProvider 实现 — ServiceBackedDataProvider.

Facade 模式：组合 MarketService + MetadataService + DerivedQueryService，
满足 kernel.DataProvider Protocol，为 core 层提供统一数据访问。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from ditto_kernel.provider import AnyFrame, BarQuery, InstrumentQuery

from ditto_datahub.services.market_service import AdjType, MarketBarsQuery

if TYPE_CHECKING:
    from ditto_datahub.services.derived.query_service import DerivedQueryService
    from ditto_datahub.services.market_service import MarketService
    from ditto_datahub.services.metadata_service import MetadataService

__all__ = ["ServiceBackedDataProvider"]


class ServiceBackedDataProvider:
    """
    组合 MarketService + MetadataService + DerivedQueryService 的 DataProvider 实现.

    命名为 ServiceBacked（Facade 模式）而非 Adapter（非接口转换）。
    """

    def __init__(
        self,
        *,
        market_service: MarketService,
        metadata_service: MetadataService,
        derived_service: DerivedQueryService,
    ) -> None:
        self._market = market_service
        self._metadata = metadata_service
        self._derived = derived_service

    def get_bars(self, query: BarQuery) -> AnyFrame:
        """
        获取行情数据.

        自动将 string ticker 解析为 int instrument_id，
        然后委托给 MarketService.find_bars。
        """
        ticker_to_id = self._metadata.resolve_instrument_ids_batch(
            identifiers=list(query.instruments),
            source="tushare",
            asof=None,
        )
        instrument_ids = [
            ticker_to_id[ticker]
            for ticker in query.instruments
            if ticker in ticker_to_id
        ]

        if not instrument_ids:
            return pl.DataFrame()

        bars_query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=query.start,
            end=query.end,
            adj=AdjType.from_string(query.adj),
        )
        return self._market.find_bars(bars_query)

    def get_instruments(self, query: InstrumentQuery) -> AnyFrame:
        """获取标的列表."""
        return self._metadata.find_securities(
            None,
            asset_class=query.asset_class,
            exchange=query.exchange,
        )

    def get_schedule(self, start: str, end: str) -> AnyFrame:
        """获取交易日历."""
        return self._metadata.list_calendar_range(start, end, only_open=True)

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
    ) -> AnyFrame:
        """获取因子数据."""
        ticker_to_id = self._metadata.resolve_instrument_ids_batch(
            identifiers=list(instruments),
            source="tushare",
            asof=None,
        )
        instrument_ids = tuple(
            ticker_to_id[t] for t in instruments if t in ticker_to_id
        )

        if not instrument_ids:
            return pl.DataFrame()

        return self._derived.query_for_evaluation(
            derived_ids=(name,),
            instrument_ids=instrument_ids,
            start=start,
            end=end,
        )
