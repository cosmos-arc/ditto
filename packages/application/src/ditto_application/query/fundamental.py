"""Fundamental query facade — 封装 FundamentalService，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_data.services.fundamental_service import FundamentalService

__all__ = ["FundamentalQueryFacade"]


class FundamentalQueryFacade:
    """
    Fundamental 域查询 facade.

    封装 FundamentalService，隐藏 CQRS 端口类型，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(self, fundamental_service: FundamentalService) -> None:
        self._service = fundamental_service

    def get_balance_sheet(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """
        查询资产负债表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            资产负债表 DataFrame，无数据返回 None

        """
        return self._service.get_balance_sheet(instrument_id, as_of_date)

    def get_income_statement(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """
        查询利润表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            利润表 DataFrame，无数据返回 None

        """
        return self._service.get_income_statement(instrument_id, as_of_date)

    def get_cash_flow(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """
        查询现金流量表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            现金流量表 DataFrame，无数据返回 None

        """
        return self._service.get_cash_flow(instrument_id, as_of_date)

    def get_dividend(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """
        查询股息数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期

        Returns:
            股息 DataFrame，无数据返回 None

        """
        return self._service.get_dividend(instrument_id, as_of_date)

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """
        查询公司行动数据.

        Args:
            instrument_id: 标的 ID
            start_date: 开始日期
            end_date: 结束日期
            as_of_date: PIT 查询日期（可选）

        Returns:
            公司行动 DataFrame

        """
        return self._service.list_corporate_actions(
            instrument_id, start_date, end_date, as_of_date
        )
