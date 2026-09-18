"""
基本面数据获取 — 从 TushareSource 提取的基本面 fetch 逻辑.

提供 fetch_balance_sheet / fetch_income_statement / fetch_cash_flow /
fetch_dividend / fetch_corporate_actions 模块级函数，
供 TushareSource 的同名方法委托调用。

财务三表披露锚 = f_ann_date（实际公告日，ADR 红线 4）。实测约束：
- f_ann_date ≥ ann_date 在近期数据恒成立（2016 年后 12 组抽样零反例；
  2005 年存在少量 f_ann < ann 历史行，方向为更早披露，PIT 安全），
  漂移可达数千天（年报更正公告），不能以 ann_date 窗口作为披露事件边界；
- 数据代理不支持 f_ann_date 过滤参数，但支持 period 报告期过滤。
故披露增量统一按"近期报告期超集拉取 + 本地按 knowledge_date 过滤"，
未来行（knowledge_date > 截止日）在 fetch 层剔除，null 行保留交给
sparse PIT fail-closed 校验。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import polars as pl

from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter

# ponytail: 8 季度窗口覆盖正常披露滞后与常见更正；实测极端更正可滞后
# 9 年（2016 年报 2025 年更正），超出窗口的老期更正不在增量可见范围，
# 需扩大窗口或按 period 全量重建。
_DISCLOSURE_PERIOD_WINDOW = 8
_QUARTER_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


def _recent_quarter_ends(
    trade_date: str,
    count: int = _DISCLOSURE_PERIOD_WINDOW,
) -> list[str]:
    """Trailing quarter-end periods (compact dates) at or before trade_date."""
    d = date.fromisoformat(trade_date)
    year, quarter_idx = d.year, (d.month - 1) // 3 - 1  # 最近已完结季度
    if quarter_idx < 0:  # 当季首月仍处上一年 Q4 之后
        year, quarter_idx = d.year - 1, 3
    ends: list[str] = []
    for _ in range(count):
        end_month = quarter_idx * 3 + 3  # 季度末月 3/6/9/12
        quarter_end = date(year, end_month, _QUARTER_END_DAY[end_month])
        ends.append(quarter_end.strftime("%Y%m%d"))
        quarter_idx -= 1
        if quarter_idx < 0:
            year -= 1
            quarter_idx = 3
    return ends


def _fetch_disclosure_delta(
    vip_fetch: Callable[..., pl.DataFrame],
    *,
    asof_date: date,
    start_date: date | None = None,
) -> pl.DataFrame:
    """
    Pull trailing report periods and keep only rows knowable by the cutoff.

    knowledge_date 为 null 的行保留，交由 sparse PIT 校验 fail-closed 拒收。
    """
    frames = [
        vip_fetch(period=period)
        for period in _recent_quarter_ends(asof_date.isoformat())
    ]
    merged = pl.concat(frames, how="diagonal_relaxed")
    knowledge = pl.col("knowledge_date")
    if start_date is None:
        knowable = knowledge.is_null() | (knowledge <= pl.lit(asof_date))
    else:
        knowable = knowledge.is_null() | knowledge.is_between(
            pl.lit(start_date), pl.lit(asof_date), closed="both"
        )
    return merged.filter(knowable)


def _knowable_by_end(result: pl.DataFrame, end_date: str) -> pl.DataFrame:
    """Keep rows whose disclosure anchor is not after end_date (nulls preserved)."""
    knowledge = pl.col("knowledge_date")
    return result.filter(
        knowledge.is_null() | (knowledge <= pl.lit(date.fromisoformat(end_date)))
    )


def fetch_disclosure_range(
    vip_fetch: Callable[..., pl.DataFrame],
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """
    Fetch disclosure events with knowledge_date inside [start_date, end_date].

    报告期超集拉取后按披露锚过滤区间；与单日增量共用同一窗口语义。
    """
    return _fetch_disclosure_delta(
        vip_fetch,
        asof_date=_parse_iso(end_date),
        start_date=_parse_iso(start_date),
    )


def _parse_iso(value: str) -> date:
    return date.fromisoformat(value)


def _require_statement_mode(
    *,
    trade_date: str | None,
    source_ticker: str | None,
) -> None:
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")


def _require_ticker_range(
    *,
    source_ticker: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, str, str]:
    if not source_ticker or not start_date or not end_date:
        raise ValueError("按标的查询必须指定 source_ticker、start_date 和 end_date")
    return source_ticker, start_date, end_date


def _fetch_statement(
    to_compact_date: Callable[[str], str],
    *,
    vip_fetch: Callable[..., pl.DataFrame],
    standard_fetch: Callable[..., pl.DataFrame],
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Financial-statement fetch shared by balance sheet / income / cash flow.

    披露增量模式（trade_date）：按近期报告期超集拉取，保留 knowledge_date
    ≤ trade_date 的行；按标的模式：ann_date 窗口拉取后剔除披露晚于
    end_date 的行。两种模式均保留 null knowledge_date 行交由 PIT 校验拒收。
    """
    _require_statement_mode(trade_date=trade_date, source_ticker=source_ticker)
    if trade_date:
        return _fetch_disclosure_delta(
            vip_fetch,
            asof_date=_parse_iso(trade_date),
        )
    source_ticker, start_date, end_date = _require_ticker_range(
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )
    result = standard_fetch(
        ts_code=source_ticker,
        start_date=to_compact_date(start_date),
        end_date=to_compact_date(end_date),
    )
    return _knowable_by_end(result, end_date)


def fetch_balance_sheet(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch balance sheet data (f_ann_date disclosure anchor)."""
    return _fetch_statement(
        to_compact_date,
        vip_fetch=fundamental.fetch_balance_sheet_vip,
        standard_fetch=fundamental.fetch_balance_sheet,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_income_statement(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch income statement data (f_ann_date disclosure anchor)."""
    return _fetch_statement(
        to_compact_date,
        vip_fetch=fundamental.fetch_income_statement_vip,
        standard_fetch=fundamental.fetch_income_statement,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_cash_flow(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch cash flow data (f_ann_date disclosure anchor)."""
    return _fetch_statement(
        to_compact_date,
        vip_fetch=fundamental.fetch_cash_flow_vip,
        standard_fetch=fundamental.fetch_cash_flow,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_dividend(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch dividend data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 除权除息日 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with dividend SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询
        compact_date = to_compact_date(trade_date)
        return fundamental.fetch_dividend(ex_date=compact_date)

    result = fundamental.fetch_dividend(ts_code=source_ticker)
    if result.is_empty() or start_date is None or end_date is None:
        return result
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    return result.filter(
        pl.col("knowledge_date").is_not_null()
        & pl.col("knowledge_date").is_between(start, end, closed="both")
    )


def fetch_corporate_actions(
    fundamental: FundamentalTushareAdapter,
    to_compact_date: Callable[[str], str],
    trade_date: str,
) -> pl.DataFrame:
    """
    Fetch corporate actions data.

    Args:
        fundamental: Fundamental 数据适配器.
        to_compact_date: 日期格式转换函数（YYYY-MM-DD → YYYYMMDD）.
        trade_date: 交易日期 (YYYY-MM-DD).

    Returns:
        DataFrame with corporate_actions SourceSchema fields.

    """
    compact_date = to_compact_date(trade_date)
    return fundamental.fetch_corporate_actions(
        ann_date=compact_date,
    )
