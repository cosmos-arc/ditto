"""Capital query facade — 封装 capital 数据端口，隐藏内部端口类型."""

from __future__ import annotations

from datetime import date
from typing import Protocol

import polars as pl

from ditto_application.queries._maturity_gate import assert_query_datasets_allowed

__all__ = ["CapitalDataPort", "CapitalQueryFacade"]

_MARGIN_TRADING_DATASET = "margin_trading"
_VALUATION_METRICS_DATASET = "valuation_metrics"
_MONEYFLOW_DATASET = "moneyflow"
_CYQ_PERF_DATASET = "cyq_perf"
_TOP_LIST_DATASET = "top_list"
_TOP_INST_DATASET = "top_inst"


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

    def get_moneyflows(self, start: str, end: str) -> pl.DataFrame:
        """查询全市场资金流向帧（L3 巡检）."""
        ...

    def get_moneyflow(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """逐标的资金流窗口读（画像链）."""
        ...

    def get_top_list(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """逐标的龙虎榜窗口读（画像链）."""
        ...

    def get_top_inst(self, instrument_id: int, start: str, end: str) -> pl.DataFrame:
        """逐标的龙虎榜席位窗口读（画像链）."""
        ...

    def get_margin_trading_range(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """逐标的两融窗口读（PIT 可选；画像链）."""
        ...

    def get_cyq_perfs(self, start: str, end: str) -> pl.DataFrame:
        """查询全市场每日筹码及胜率帧（L3 巡检）."""
        ...


class CapitalQueryFacade:
    """
    Capital 域查询 facade.

    通过 CapitalDataPort Protocol 获取 capital 数据，
    对外只暴露原始参数和 pl.DataFrame 返回值。
    """

    def __init__(
        self,
        capital_store: CapitalDataPort,
    ) -> None:
        self._service = capital_store

    def get_margin_trading(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询融资融券数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            融资融券 DataFrame

        """
        self._assert_dataset_allowed(
            _MARGIN_TRADING_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_margin_trading(instrument_id, as_of_date)

    def get_moneyflows(
        self,
        *,
        start: str,
        end: str,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """查询全市场资金流向帧（L3 巡检用，金额万元/量手）."""
        self._assert_dataset_allowed(
            _MONEYFLOW_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_moneyflows(start, end)

    def get_cyq_perfs(
        self,
        *,
        start: str,
        end: str,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """查询全市场每日筹码及胜率帧（L3 巡检用）."""
        self._assert_dataset_allowed(
            _CYQ_PERF_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_cyq_perfs(start, end)

    def get_moneyflow(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的资金流窗口读（万元/手；#658 批次3 画像链）."""
        self._assert_dataset_allowed(
            _MONEYFLOW_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_moneyflow(instrument_id, start, end)

    def get_top_list(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的龙虎榜窗口读（事件按 reason 独立成行）."""
        self._assert_dataset_allowed(
            _TOP_LIST_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_top_list(instrument_id, start, end)

    def get_top_inst(
        self,
        instrument_id: int,
        start: str,
        end: str,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的龙虎榜席位窗口读（单边 null 保真）."""
        self._assert_dataset_allowed(
            _TOP_INST_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_top_inst(instrument_id, start, end)

    def get_margin_trading_range(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of_date: date | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """逐标的两融窗口读（pit_asof=as_of_date，缺省窗口终点）."""
        self._assert_dataset_allowed(
            _MARGIN_TRADING_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_margin_trading_range(
            instrument_id, start, end, as_of_date
        )

    def get_valuation_metrics(
        self,
        instrument_id: int,
        as_of_date: date,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        查询估值指标数据.

        Args:
            instrument_id: 标的 ID
            as_of_date: PIT 查询日期
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            估值指标 DataFrame

        """
        self._assert_dataset_allowed(
            _VALUATION_METRICS_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_valuation_metrics(instrument_id, as_of_date)

    def _assert_dataset_allowed(
        self,
        dataset_id: str,
        *,
        allow_experimental_data: bool,
    ) -> None:
        assert_query_datasets_allowed(
            (dataset_id,),
            allow_experimental_data=allow_experimental_data,
            context=f"capital query {dataset_id}",
        )
