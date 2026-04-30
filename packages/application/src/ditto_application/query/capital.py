"""Capital query facade — 封装 CapitalService，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_data.services.capital_service import CapitalService

__all__ = ["CapitalQueryFacade"]


class CapitalQueryFacade:
    """
    Capital 域查询 facade.

    封装 CapitalService，隐藏 CQRS 端口类型，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(self, capital_service: CapitalService) -> None:
        self._service = capital_service

    def get_margin_trading(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        查询融资融券数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            融资融券 DataFrame

        """
        return self._service.get_margin_trading(instrument_id, as_of_date)

    def get_valuation_metrics(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame:
        """
        查询估值指标数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            估值指标 DataFrame

        """
        return self._service.get_valuation_metrics(instrument_id, as_of_date)
