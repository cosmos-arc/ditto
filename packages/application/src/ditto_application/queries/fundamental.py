"""Fundamental query facade — 封装 fundamental 数据端口，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import polars as pl
from ditto_data.catalog.promotion import DatasetMaturityPromotionReader

from ditto_application.queries._maturity_gate import assert_query_datasets_allowed

__all__ = ["FundamentalDataPort", "FundamentalQueryFacade"]

_BALANCE_SHEET_DATASET = "balance_sheet"
_INCOME_STATEMENT_DATASET = "income_statement"
_CASH_FLOW_DATASET = "cash_flow"
_DIVIDEND_DATASET = "dividend"
_CORPORATE_ACTIONS_DATASET = "corporate_actions"


class FundamentalDataPort(Protocol):
    """窄 Protocol：FundamentalQueryFacade 所需的 fundamental 数据获取能力."""

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询资产负债表."""
        ...

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询利润表."""
        ...

    def get_cash_flow(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询现金流量表."""
        ...

    def get_dividend(
        self,
        instrument_id: int,
        as_of_date: date,
    ) -> pl.DataFrame | None:
        """查询股息数据."""
        ...

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """查询公司行动数据."""
        ...


class FundamentalQueryFacade:
    """
    Fundamental 域查询 facade.

    通过 FundamentalDataPort Protocol 获取 fundamental 数据，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(
        self,
        fundamental_store: FundamentalDataPort,
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
    ) -> None:
        self._service = fundamental_store
        self._maturity_promotion_reader = maturity_promotion_reader

    def get_balance_sheet(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询资产负债表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            资产负债表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _BALANCE_SHEET_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_balance_sheet(instrument_id, as_of_date)

    def get_income_statement(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询利润表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            利润表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _INCOME_STATEMENT_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_income_statement(instrument_id, as_of_date)

    def get_cash_flow(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询现金流量表.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            现金流量表 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _CASH_FLOW_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_cash_flow(instrument_id, as_of_date)

    def get_dividend(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame | None:
        """
        查询股息数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            股息 DataFrame，无数据返回 None

        """
        self._assert_dataset_allowed(
            _DIVIDEND_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_dividend(instrument_id, as_of_date)

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询公司行动数据.

        Args:
            instrument_id: 标的 ID
            start_date: 开始日期
            end_date: 结束日期
            as_of_date: PIT 查询日期（可选）
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            公司行动 DataFrame

        """
        self._assert_dataset_allowed(
            _CORPORATE_ACTIONS_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.list_corporate_actions(
            instrument_id, start_date, end_date, as_of_date
        )

    def _assert_dataset_allowed(
        self,
        dataset_id: str,
        *,
        allow_experimental_data: bool,
    ) -> None:
        assert_query_datasets_allowed(
            (dataset_id,),
            allow_experimental_data=allow_experimental_data,
            maturity_promotion_reader=self._maturity_promotion_reader,
            context=f"fundamental query {dataset_id}",
        )
