"""数据质量 Protocol 定义 — 描述 data 层质量服务的契约接口."""

from __future__ import annotations

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "QualityEngineProtocol",
    "QuarantineWriterProtocol",
    "TdxSourceProtocol",
]

from typing import Any, Literal, Protocol

import polars as pl
from ditto_kernel.quality import DQResult


class QualityEngineProtocol(Protocol):
    """质量引擎协议."""

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """执行写入时 DQ 检查."""
        ...

    def check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """执行跨源对比检查."""
        ...

    def check_statistical(
        self,
        dataset: str,
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
    ) -> DQResult:
        """执行统计类异常检查."""
        ...


class InstrumentStoreProtocol(Protocol):
    """证券信息补充协议 — instrument_id → ticker 转换."""

    def enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
        """从 instrument_id 添加 ticker 列."""
        ...


class TdxSourceProtocol(Protocol):
    """通达信数据源协议."""

    def fetch_stock_daily_bars(
        self, tickers: list[str], trade_date: str
    ) -> pl.DataFrame:
        """获取通达信股票日线数据."""
        ...


class ComparisonStoreProtocol(Protocol):
    """对账结果持久化协议."""

    def write_comparison(
        self, trade_date: str, comparison_df: pl.DataFrame, dataset: str
    ) -> None:
        """持久化对比数据."""
        ...


class QuarantineWriterProtocol(Protocol):
    """隔离写入协议."""

    def save_failed_data(
        self,
        dataset: str,
        rule_id: str,
        severity: str,
        failed_data: pl.DataFrame,
        trade_date: str | None = None,
    ) -> int:
        """持久化质量失败数据."""
        ...
