"""质量服务 — 协议与领域模型定义."""

from __future__ import annotations

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "QualityEngineProtocol",
    "ReconciliationResult",
    "TdxSourceProtocol",
]

from dataclasses import dataclass
from typing import Any, Literal, Protocol

import polars as pl
from ditto_kernel.quality import DQResult

# ---------------------------------------------------------------------------
# 领域模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    """对账结果（强类型）."""

    trade_date: str
    dataset: str
    passed: bool
    issue_count: int
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None

    def to_dict(self) -> dict[str, object]:
        """转换为字典（兼容旧代码）."""
        result: dict[str, object] = {
            "trade_date": self.trade_date,
            "dataset": self.dataset,
            "passed": self.passed,
            "issue_count": self.issue_count,
        }
        if self.skipped and self.skip_reason:
            result["skipped"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        return result


# ---------------------------------------------------------------------------
# 协议定义
# ---------------------------------------------------------------------------


class QualityEngineProtocol(Protocol):
    """质量引擎协议 — 供 interfaces 层依赖注入使用。"""

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """执行写入时 DQ 检查。"""
        ...

    def check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """执行跨源对比检查。"""
        ...

    def check_statistical(
        self,
        dataset: str,
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
    ) -> DQResult:
        """执行统计类异常检查。"""
        ...


class InstrumentStoreProtocol(Protocol):
    """证券信息补充依赖协议."""

    def enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
        """从 instrument_id 添加 ticker 列."""
        ...


class TdxSourceProtocol(Protocol):
    """通达信数据源依赖协议."""

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
        """持久化对比数据。"""
        ...
