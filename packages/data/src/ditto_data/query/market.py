"""行情查询门面 — K线、复权、因子."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from ditto_data.services.market_service import AdjType, MarketBarsQuery

if TYPE_CHECKING:
    from ditto_data.services.market_service import MarketService

__all__ = ["MarketQuerist"]


class MarketQuerist:
    """
    行情查询门面.

    组合 MarketService，提供面向消费者的简化查询接口。
    """

    def __init__(self, market_service: MarketService) -> None:
        self._service = market_service

    def get_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str,
        end: str,
        adj: str = "none",
        with_ticker: bool = False,
        with_status: bool = False,
    ) -> pl.DataFrame:
        """
        获取行情数据.

        Args:
            instrument_ids: 标的 ID 列表
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            adj: 复权类型 ("none" / "qfq" / "hfq")
            with_ticker: 是否包含 ticker 信息
            with_status: 是否包含状态信息

        Returns:
            行情 DataFrame

        """
        query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            adj=AdjType.from_string(adj),
            with_ticker=with_ticker,
            with_status=with_status,
        )
        return self._service.find_bars(query)
