"""Capital query facade — 封装 capital 数据端口，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import polars as pl

__all__ = ["CapitalDataPort", "CapitalQueryFacade"]


class CapitalDataPort(Protocol):
    """窄 Protocol：CapitalQueryFacade 所需的 capital 数据获取能力."""

    def get_margin_trading(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame:
        """查询融资融券数据."""
        ...

    def get_valuation_metrics(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame:
        """查询估值指标数据."""
        ...


class CapitalQueryFacade:
    """
    Capital 域查询 facade.

    通过 CapitalDataPort Protocol 获取 capital 数据，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(self, capital_store: CapitalDataPort) -> None:
        self._service = capital_store

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
