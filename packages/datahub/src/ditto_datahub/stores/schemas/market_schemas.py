"""Market 域的 StoreSchema 定义."""

from __future__ import annotations

import polars as pl

from ditto_datahub.stores.schemas.store_schema import StoreSchema

__all__ = [
    "ADJ_FACTOR_STORE_SCHEMA",
    "ETF_DAILY_STORE_SCHEMA",
    "INDEX_DAILY_STORE_SCHEMA",
    "STOCK_DAILY_STORE_SCHEMA",
    "STOCK_STATUS_STORE_SCHEMA",
]

STOCK_DAILY_STORE_SCHEMA = StoreSchema(
    dataset="market/stock/bars",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "pre_close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
        "pct_change": pl.Float64,
        "turnover": pl.Float64,
        "is_suspended": pl.Boolean,
        "is_limit_up": pl.Boolean,
        "is_limit_down": pl.Boolean,
        "is_st": pl.Boolean,
        "up_limit": pl.Float64,
        "down_limit": pl.Float64,
    },
)

ETF_DAILY_STORE_SCHEMA = StoreSchema(
    dataset="market/etf/bars",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "pre_close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
        "pct_change": pl.Float64,
    },
)

INDEX_DAILY_STORE_SCHEMA = StoreSchema(
    dataset="market/index/bars",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "pre_close": pl.Float64,
        "change": pl.Float64,
        "pct_change": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    },
)

ADJ_FACTOR_STORE_SCHEMA = StoreSchema(
    dataset="market/stock/adj",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
        "adj_factor": pl.Float64,
        "knowledge_date": pl.Date,
    },
)

STOCK_STATUS_STORE_SCHEMA = StoreSchema(
    dataset="market/stock/status",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "is_suspended": pl.Boolean,
        "suspend_timing": pl.Utf8,
        "is_st": pl.Boolean,
        "st_type": pl.Utf8,
        "list_status": pl.Utf8,
        "source": pl.Utf8,
        "source_ticker": pl.Utf8,
    },
)
