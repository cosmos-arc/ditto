"""期货数据源入口 — fetch 函数委托到 FuturesTushareAdapter（#434）."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.adapters.futures import FuturesTushareAdapter

__all__ = ["fetch_futures_basic", "fetch_futures_daily"]


def fetch_futures_daily(
    adapter: FuturesTushareAdapter,
    trade_date: str | None = None,
    source_ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pl.DataFrame:
    """获取期货合约日线（amount 万元、原始口径）."""
    return adapter.fetch_daily(
        trade_date=trade_date,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )


def fetch_futures_basic(adapter: FuturesTushareAdapter) -> pl.DataFrame:
    """获取期货合约信息快照（按交易所分片）."""
    return adapter.fetch_basic()
