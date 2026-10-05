"""数据质量 Protocol 定义 — 描述 data 层质量服务的契约接口."""

from __future__ import annotations

from typing import Any, Literal, Protocol

import polars as pl

from ditto_data.quality.checkers.cross_source import CrossSourceComparison
from ditto_data.quality.quality_types import DQResult

__all__ = [
    "AdjFactorReconcileContextProtocol",
    "ComparisonStoreProtocol",
    "ExDividendInstrumentSourceProtocol",
    "FinancialReconcileContextProtocol",
    "InstrumentStoreProtocol",
    "QualityEngineProtocol",
    "QuarantineWriterProtocol",
    "SecondaryAdjustmentEventsSourceProtocol",
    "SecondaryBarsSourceProtocol",
    "SecondaryFinancialsSourceProtocol",
    "SecondaryIdentityResolverProtocol",
]


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

    def compare_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> CrossSourceComparison:
        """执行跨源对比并返回结构化报告（两侧数量/匹配/未匹配/重复键/差异）."""
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

    def has_statistical_rules(self, dataset: str) -> bool:
        """Return whether the configured dataset has applicable L3 rules."""
        ...


class InstrumentStoreProtocol(Protocol):
    """证券信息补充协议 — instrument_id → ticker 转换."""

    def enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
        """从 instrument_id 添加 ticker 列."""
        ...


class SecondaryBarsSourceProtocol(Protocol):
    """对账辅源协议 — 日线值跨源对比的次源取数（fuyao）。"""

    def fetch_stock_daily_bars(
        self, tickers: list[str], trade_date: str
    ) -> pl.DataFrame:
        """获取辅源股票日线数据 [ticker, trade_date, OHLCV, amount]."""
        ...


class SecondaryAdjustmentEventsSourceProtocol(Protocol):
    """adj_factor 对账辅源协议 — 公司行动事件流取数（fuyao 本地 dump，#438）。"""

    def fetch_adjustment_events(self, trade_date: str) -> pl.DataFrame:
        """
        获取辅源除权事件 [ticker, trade_date, 分红/送转/配股字段].

        事件字段保持公司行动原始口径（无单位换算），ticker 为裸码。
        """
        ...


class SecondaryFinancialsSourceProtocol(Protocol):
    """财务三表对账辅源协议 — 财务数值取数（fuyao REST，#473）。"""

    def fetch_financial_statements(
        self,
        dataset: str,
        thscodes: list[str],
        *,
        period: str = "quarterly",
        limit: int = 20,
    ) -> pl.DataFrame:
        """
        获取辅源财务报表行.

        列为 [ticker(完整 thscode), report_date, disclosure_date, fiscal_year,
        fiscal_period, <内部列名数值字段>]；金额两侧均为元（无单位换算）；
        disclosure_date 为辅源披露日，仅用于 vintage 判定（#473 红线：
        交叉不得跨 vintage 混比）。
        """
        ...


class FinancialReconcileContextProtocol(Protocol):
    """财务对账主源上下文 — 最新有效 vintage 报表行（#473）。"""

    def latest_statements(self, dataset: str, as_of: str) -> pl.DataFrame:
        """
        获取主源最新有效 vintage 报表行.

        列为 [instrument_id, ticker, report_date, knowledge_date, <数值字段>]
        （PIT 有效区间过滤后的每报告期最新 vintage）。比较范围按黄金集标的
        收敛（黄金集未配置时拒绝——财务对账不做全市场展开）；knowledge_date
        = 披露锚 f_ann_date（#199/#191 红线：辅源披露日只做交叉对账，不进
        披露链）。
        """
        ...


class AdjFactorReconcileContextProtocol(Protocol):
    """adj_factor 对账主源上下文 — 因子窗口与同基准前收（#438）。"""

    def factor_window(self, trade_date: str) -> pl.DataFrame:
        """主源累积因子回看窗 [instrument_id, trade_date, adj_factor]。"""
        ...

    def previous_closes(self, trade_date: str) -> pl.DataFrame:
        """主源同基准前收 [instrument_id, prev_close]（目标日前最后一根收盘）。"""
        ...


class SecondaryIdentityResolverProtocol(Protocol):
    """辅源身份反解协议 — 辅源代码 → instrument_id（只读，#395）。"""

    def resolve_secondary_ids(
        self, source_tickers: list[str], source: str, *, asof: str
    ) -> dict[str, int]:
        """
        把辅源代码（如 fuyao thscode/裸码）反解为 instrument_id.

        只读：既有来源映射优先，缺失时按裸码前缀规则唯一匹配已注册
        instrument；无法唯一匹配的键不返回（行保持未匹配）。
        """
        ...


class ExDividendInstrumentSourceProtocol(Protocol):
    """除权日（adj_factor 事件日）标的来源协议."""

    def ex_dividend_instruments(self, trade_date: str) -> frozenset[int]:
        """返回该交易日发生 adj_factor 变化的 instrument_id 集合."""
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
