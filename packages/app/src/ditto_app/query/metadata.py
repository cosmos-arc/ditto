"""Metadata query facade — 封装 MetadataService，隐藏 SecurityQuery 等内部类型."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_data.services.metadata_service import MetadataService

__all__ = ["MetadataQueryFacade"]


class MetadataQueryFacade:
    """
    Metadata 域查询 facade.

    封装 MetadataService，隐藏 SecurityQuery 等内部查询类型，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def get_instrument(self, instrument_id: int) -> dict[str, Any] | None:
        """
        获取单个证券信息.

        Args:
            instrument_id: 标的 ID

        Returns:
            证券信息字典，不存在返回 None

        """
        return self._service.get_instrument(instrument_id)

    def find_securities(
        self,
        *,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        source_tickers: list[str] | None = None,
    ) -> pl.DataFrame:
        """
        多维查询证券数据.

        Args:
            asset_class: 资产类别过滤
            exchange: 交易所过滤
            is_active: 活跃状态过滤
            source_tickers: 源代码列表

        Returns:
            证券数据 DataFrame

        """
        return self._service.find_securities(
            source_tickers=source_tickers,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
        )

    def resolve_instrument_identifier(
        self,
        *,
        instrument_id: int | None = None,
        standard_ticker: str | None = None,
        ticker: str | None = None,
        asset_class: str | None = None,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        统一标识符解析.

        Args:
            instrument_id: 标的 ID
            standard_ticker: 标准代码
            ticker: 裸代码
            asset_class: 资产类别
            source: 数据源
            asof: PIT 日期

        Returns:
            instrument_id 或 None

        """
        result = self._service.resolve_instrument_identifier(
            instrument_id=instrument_id,
            standard_ticker=standard_ticker,
            ticker=ticker,
            asset_class=asset_class,
            source=source,
            asof=asof,
        )
        return int(result) if result is not None else None

    def resolve_source_ticker(
        self,
        *,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str = "stock",
        source: str = "tushare",
        asof: str | None = None,
    ) -> str:
        """
        将任意标识符解析为 source_ticker.

        Args:
            ticker: 裸代码
            standard_ticker: 标准代码
            instrument_id: 标的 ID
            asset_class: 资产类别
            source: 数据源
            asof: PIT 日期

        Returns:
            source ticker 字符串

        """
        return self._service.resolve_source_ticker(
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            asset_class=asset_class,
            source=source,
            asof=asof,
        )

    def is_trading_day(self, date: str) -> bool:
        """
        判断是否为交易日.

        Args:
            date: 日期 (YYYY-MM-DD)

        Returns:
            是否为交易日

        """
        return self._service.is_trading_day(date)

    def get_last_trading_day(self) -> str | None:
        """
        获取最后一个交易日.

        Returns:
            最后交易日的日期字符串，不存在返回 None

        """
        return self._service.get_last_trading_day()

    def list_calendar_range(
        self,
        *,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        查询日历范围.

        Args:
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            only_open: 是否只返回交易日

        Returns:
            日历 DataFrame

        """
        return self._service.list_calendar_range(
            start=start,
            end=end,
            only_open=only_open,
        )
