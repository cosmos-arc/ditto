"""
Schema definitions for Parquet datasets.

This module contains Polars schema definitions for all datasets
stored in Parquet format. Each schema defines the column names
and their corresponding Polars data types.

Following the design document at docs/design/02_data_design.md
"""

import polars as pl

# ============================================================
# Stock Daily Schema
# ============================================================
# Note: Renamed from MARKET_DAILY to STOCK_DAILY per user request
# to clarify this table only contains stock data.
STOCK_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "src_code": pl.Utf8,
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
}


# ============================================================
# ETF Daily Schema
# ============================================================
ETF_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "src_code": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
    "pct_change": pl.Float64,
}


# ============================================================
# Index Daily Schema
# ============================================================
INDEX_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "src_code": pl.Utf8,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "pre_close": pl.Float64,
    "change": pl.Float64,
    "pct_change": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


# ============================================================
# Adjustment Factor Schema
# ============================================================
ADJ_FACTOR_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "source": pl.Utf8,
    "src_code": pl.Utf8,
    "adj_factor": pl.Float64,
}


# ============================================================
# Index Weight Schema
# ============================================================
INDEX_WEIGHT_SCHEMA: dict[str, type[pl.DataType]] = {
    "index_sid": pl.Int64,
    "con_sid": pl.Int64,
    "trade_date": pl.Date,
    "weight": pl.Float64,
    "source": pl.Utf8,
    "index_code": pl.Utf8,
    "con_code": pl.Utf8,
}


# ============================================================
# Universe Constituent Schema (PIT)
# ============================================================
UNIVERSE_CONSTITUENT_SCHEMA: dict[str, type[pl.DataType]] = {
    "universe_id": pl.Utf8,
    "sid": pl.Int64,
    "source": pl.Utf8,
    "src_code": pl.Utf8,
    "effective_from": pl.Date,
    "effective_to": pl.Date,
    "weight": pl.Float64,
}
