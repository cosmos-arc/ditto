"""Futures query facade — 期货双库（日线/合约身份）消费接线（#658 批次4c）."""

from __future__ import annotations

from typing import Protocol

import polars as pl

from ditto_application.queries._maturity_gate import assert_query_datasets_allowed

__all__ = ["FuturesDataPort", "FuturesQueryFacade"]

_FUTURES_DAILY_DATASET = "futures_daily"
_FUTURES_BASIC_DATASET = "futures_basic"


class FuturesDataPort(Protocol):
    """窄 Protocol：FuturesQueryFacade 所需的期货数据获取能力."""

    def get_futures_daily(
        self,
        start: str | None,
        end: str | None,
        source_tickers: list[str] | None = None,
    ) -> pl.DataFrame:
        """期货合约日线窗口读."""
        ...

    def get_futures_contracts(
        self,
        exchange: str | None = None,
        fut_code: str | None = None,
    ) -> pl.DataFrame:
        """期货合约身份快照读."""
        ...


class FuturesQueryFacade:
    """
    Futures 域查询 facade.

    通过 FuturesDataPort Protocol 获取期货数据（合约以 source_ticker 为键，
    不映射 instrument_id——期货合约不是证券主数据标的），对外只暴露原始
    参数和 pl.DataFrame 返回值。
    """

    def __init__(self, futures_data: FuturesDataPort) -> None:
        self._service = futures_data

    def get_futures_daily(
        self,
        start: str | None,
        end: str | None,
        source_tickers: list[str] | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        期货合约日线窗口读（latest_available；amount 万元）.

        Args:
            start: 窗口开始 (YYYY-MM-DD；None 为不设下界)
            end: 窗口结束 (YYYY-MM-DD；None 为不设上界)
            source_tickers: 合约代码过滤（可选，ts_code 形态如 "RB2410.SHF"）
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            期货日线 DataFrame（source_ticker、trade_date、OHLC、settle、
            pre_settle、volume、amount、open_interest）

        """
        self._assert_dataset_allowed(
            _FUTURES_DAILY_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_futures_daily(start, end, source_tickers)

    def get_futures_contracts(
        self,
        exchange: str | None = None,
        fut_code: str | None = None,
        *,
        allow_experimental_data: bool = False,
    ) -> pl.DataFrame:
        """
        期货合约身份快照读（与日线同范围，含已到期合约）.

        Args:
            exchange: 交易所过滤（可选，如 "SHFE"）
            fut_code: 品种代码过滤（可选，如 "RB"）
            allow_experimental_data: 显式允许 experimental 数据集进入研究态查询

        Returns:
            合约身份 DataFrame（source_ticker、symbol、exchange、fut_code、
            multiplier、list_date、delist_date）

        """
        self._assert_dataset_allowed(
            _FUTURES_BASIC_DATASET,
            allow_experimental_data=allow_experimental_data,
        )
        return self._service.get_futures_contracts(exchange, fut_code)

    def _assert_dataset_allowed(
        self,
        dataset_id: str,
        *,
        allow_experimental_data: bool,
    ) -> None:
        assert_query_datasets_allowed(
            (dataset_id,),
            allow_experimental_data=allow_experimental_data,
            context=f"futures query {dataset_id}",
        )
