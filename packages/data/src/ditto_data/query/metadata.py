"""元数据查询门面 — 交易日历、标的、Universe."""

from __future__ import annotations

from typing import Any

import polars as pl

from ditto_data.services.metadata_service import MetadataService

__all__ = ["MetadataQuerist"]


class MetadataQuerist:
    """
    元数据查询门面.

    组合 MetadataService，提供面向消费者的简化查询接口。
    """

    def __init__(self, metadata_service: MetadataService) -> None:
        self._service = metadata_service

    def list_trading_days(
        self,
        start: str,
        end: str,
        *,
        only_open: bool = True,
    ) -> list[str]:
        """
        获取交易日历.

        Args:
            start: 开始日期 (YYYY-MM-DD)
            end: 结束日期 (YYYY-MM-DD)
            only_open: 是否仅返回开市日

        Returns:
            交易日列表

        """
        return self._service.list_trading_days(start, end, only_open=only_open)

    def find_securities(self, **kwargs: Any) -> pl.DataFrame:
        """
        查询证券列表.

        参数透传给 MetadataService.find_securities。
        """
        return self._service.find_securities(None, **kwargs)

    def list_instrument_ids(self, asset_class: str | None = None) -> list[int]:
        """
        列出所有 instrument_id.

        Args:
            asset_class: 资产类别过滤（如 "stock", "etf"）

        Returns:
            instrument_id 列表

        """
        return self._service.list_instrument_ids(asset_class=asset_class)
