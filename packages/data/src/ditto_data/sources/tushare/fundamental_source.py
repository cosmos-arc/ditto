"""
Fundamental + Capital 数据获取 — 从 TushareSource 提取的基本面/资金 fetch 逻辑.

提供 fetch_balance_sheet / fetch_income_statement / fetch_cash_flow /
fetch_dividend / fetch_corporate_actions / fetch_valuation_metrics /
fetch_margin_trading / fetch_pledge_ratio 模块级函数，
供 TushareSource 的同名方法委托调用。
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from ditto_data.sources.tushare._fundamental import (
    _fetch_disclosure_delta,
    _parse_iso,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_balance_sheet as _fetch_balance_sheet,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_cash_flow as _fetch_cash_flow,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_corporate_actions as _fetch_corporate_actions,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_dividend as _fetch_dividend,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_fina_indicator as _fetch_fina_indicator,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_fund_portfolio as _fetch_fund_portfolio,
)
from ditto_data.sources.tushare._fundamental import (
    fetch_income_statement as _fetch_income_statement,
)
from ditto_data.sources.tushare._utils import to_compact_date
from ditto_data.sources.tushare.adapters.capital import CapitalTushareAdapter
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter


def fetch_balance_sheet(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch balance sheet data（委托给 _fundamental 模块）."""
    return _fetch_balance_sheet(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_income_statement(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch income statement data（委托给 _fundamental 模块）."""
    return _fetch_income_statement(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_cash_flow(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch cash flow data（委托给 _fundamental 模块）."""
    return _fetch_cash_flow(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_dividend(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch dividend data（委托给 _fundamental 模块）."""
    return _fetch_dividend(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_corporate_actions(
    fundamental: FundamentalTushareAdapter,
    trade_date: str,
) -> pl.DataFrame:
    """Fetch corporate actions data（委托给 _fundamental 模块）."""
    return _fetch_corporate_actions(
        fundamental,
        to_compact_date,
        trade_date,
    )


# ── Capital 相关方法（估值/融资融券/质押） ──────────────────────────


def fetch_valuation_metrics(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch valuation metrics data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        capital: Capital 数据适配器.
        trade_date: 交易日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with valuation_metrics SourceSchema fields.

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
        return capital.fetch_valuation_metrics(trade_date=compact_date)

    compact_start = to_compact_date(start_date) if start_date else None
    compact_end = to_compact_date(end_date) if end_date else None
    return capital.fetch_valuation_metrics(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def fetch_margin_trading(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch margin trading data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker + start_date + end_date

    Args:
        capital: Capital 数据适配器.
        trade_date: 交易日期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with margin_trading SourceSchema fields.

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
        return capital.fetch_margin_trading(trade_date=compact_date)

    compact_start = to_compact_date(start_date) if start_date else None
    compact_end = to_compact_date(end_date) if end_date else None
    return capital.fetch_margin_trading(
        ts_code=source_ticker,
        start_date=compact_start,
        end_date=compact_end,
    )


def _pledge_snapshot_date(trade_date: str) -> str:
    """
    Resolve the pledge_stat weekly snapshot date on or before ``trade_date``.

    pledge_stat 按周发布（快照日为周五），``end_date`` 为精确匹配语义；
    交易日 D 的请求统一解析为 ≤D 的最近周五，非快照日不发起空请求。
    """
    day = date.fromisoformat(trade_date)
    snapshot = day - timedelta(days=(day.weekday() - 4) % 7)
    return snapshot.strftime("%Y%m%d")


def fetch_pledge_ratio(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch pledge ratio data.

    Supports two query modes:
    - By date batch: Specify trade_date
    - By ticker + date range: Specify source_ticker (start_date/end_date ignored)

    Args:
        capital: Capital 数据适配器.
        trade_date: 报告期 (YYYY-MM-DD). Mutually exclusive with source_ticker.
        source_ticker: Source code (e.g., "000001.SZ").
        start_date: Start date (YYYY-MM-DD). Used with source_ticker.
        end_date: End date (YYYY-MM-DD). Used with source_ticker.

    Returns:
        DataFrame with pledge_ratio SourceSchema fields.

    Raises:
        ValueError: Invalid parameter combination.
        SourceFetchError: If fetch fails.

    """
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")

    if trade_date:
        # 按日期批量查询：解析为 ≤trade_date 的最近周快照日（#512），
        # 同一快照日被重复拉取时由 (instrument_id, report_date, knowledge_date)
        # 主键幂等去重。
        return capital.fetch_pledge_ratio(report_date=_pledge_snapshot_date(trade_date))

    # 按标的查询（pledge_ratio API 不支持日期范围）
    return capital.fetch_pledge_ratio(ts_code=source_ticker)


def fetch_earnings_forecast(
    fundamental: FundamentalTushareAdapter,
    *,
    ann_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch earnings forecasts (net-profit bounds in 万元; #434)."""
    return fundamental.fetch_earnings_forecast(
        ann_date=ann_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_earnings_express(
    fundamental: FundamentalTushareAdapter,
    *,
    ann_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch earnings express reports (amounts in 元; #434)."""
    return fundamental.fetch_earnings_express(
        ann_date=ann_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_moneyflow(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 个股资金流向（金额万元/量手，#518）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_moneyflow(trade_date=trade_date)
    return capital.fetch_moneyflow(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_cyq_perf(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 每日筹码及胜率（#523）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_cyq_perf(trade_date=trade_date)
    return capital.fetch_cyq_perf(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_hk_hold(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 沪深港通持股（#520）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_hk_hold(trade_date=trade_date)
    return capital.fetch_hk_hold(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_hsgt_top10(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 沪深港通十大成交股（#520）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_hsgt_top10(trade_date=trade_date)
    return capital.fetch_hsgt_top10(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_top_list(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 龙虎榜个股明细（#519）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_top_list(trade_date=trade_date)
    return capital.fetch_top_list(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_top_inst(
    capital: CapitalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch 龙虎榜席位明细（#519）."""
    if trade_date and source_ticker:
        raise ValueError("trade_date 和 source_ticker 互斥, 不能同时指定")
    if not trade_date and not source_ticker:
        raise ValueError("必须指定 trade_date 或 source_ticker 之一")
    if trade_date:
        return capital.fetch_top_inst(trade_date=trade_date)
    return capital.fetch_top_inst(
        ts_code=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_fina_indicator(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """
    Fetch official financial indicators（#521 披露增量语义）.

    日更走 fina_indicator_vip 按 period 批量（代理 transport 非 VIP 端点
    必填 ts_code，2026-10-06 实测）；按标的回填走非 VIP 端点。
    """
    if trade_date:
        return _fetch_disclosure_delta(
            fundamental.fetch_fina_indicator_vip,
            asof_date=_parse_iso(trade_date),
        )
    return _fetch_fina_indicator(
        fundamental,
        to_compact_date,
        trade_date=None,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_fund_portfolio(
    fundamental: FundamentalTushareAdapter,
    *,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """Fetch fund quarterly holdings（#522 公告日驱动）."""
    return _fetch_fund_portfolio(
        fundamental,
        to_compact_date,
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )
