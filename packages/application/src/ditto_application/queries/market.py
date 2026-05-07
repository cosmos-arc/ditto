"""Market query facade — 封装 MarketService，隐藏内部查询类型."""

from __future__ import annotations

import polars as pl
from ditto_data.services.market_service import AdjType, MarketBarsQuery, MarketService

from ditto_application.exceptions import AppQueryError

__all__ = ["MarketQueryFacade"]

# 支持的复权类型
_VALID_ADJ_TYPES = frozenset({"none", "qfq", "hfq"})


class MarketQueryFacade:
    """
    行情数据查询 facade.

    封装 MarketService，隐藏 MarketBarsQuery / AdjType 等内部类型，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(self, market_service: MarketService) -> None:
        self._service = market_service

    def find_bars(
        self,
        *,
        instrument_ids: list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
        adj: str = "none",
        market_wide: bool = False,
        asset_class: str | None = None,
    ) -> pl.DataFrame:
        """
        查询 K 线数据（通过 MarketBarsQuery）.

        Args:
            instrument_ids: 标的 ID 列表（market_wide=True 时可为 None）
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            adj: 复权类型 ("none" | "qfq" | "hfq")
            market_wide: 全市场查询模式
                （为 True 且 instrument_ids 为空时获取所有活跃证券）
            asset_class: 资产类别过滤

        Returns:
            K 线数据 DataFrame

        Raises:
            ValueError: adj 参数不合法

        """
        if adj not in _VALID_ADJ_TYPES:
            msg = f"adj must be one of {_VALID_ADJ_TYPES}, got '{adj}'"
            raise AppQueryError(msg)

        query = MarketBarsQuery(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            adj=AdjType(adj),
            market_wide=market_wide,
            asset_class=asset_class,
        )
        return self._service.find_bars(query)

    def list_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        asset_class: str | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame:
        """
        查询 K 线数据（直接参数）.

        Args:
            instrument_ids: 标的 ID 列表
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            asset_class: 资产类别过滤
            limit: 返回数量限制

        Returns:
            K 线数据 DataFrame

        """
        return self._service.list_bars(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
            asset_class=asset_class,
            limit=limit,
        )

    def get_constituents(
        self,
        index_id: int,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        查询指数成分股.

        Args:
            index_id: 指数标的 ID
            as_of_date: 查询日期 (YYYY-MM-DD)

        Returns:
            成分股 DataFrame

        """
        return self._service.get_constituents(index_id, as_of_date)
