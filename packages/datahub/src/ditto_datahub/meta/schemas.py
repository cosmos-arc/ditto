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
    "up_limit": pl.Float64,  # 涨停价
    "down_limit": pl.Float64,  # 跌停价
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
    # PIT safety: knowledge_date = when this factor became known
    # For Tushare, this is typically trade_date + 1 day (T+1 publication)
    "knowledge_date": pl.Date,
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


# ============================================================
# Stock Status Schema (B.3: Risk Control Fields)
# ============================================================
# Stores stock status information for risk control:
# - Suspension (停牌): is_suspended, suspend_timing
# - ST status: is_st, st_type
# - List status: list_status (L=正常, D=退市, P=暂停)
STOCK_STATUS_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "is_suspended": pl.Boolean,  # 是否停牌
    "suspend_timing": pl.Utf8,  # 停牌时间段 "09:30-10:00" or None
    "is_st": pl.Boolean,  # 是否ST
    "st_type": pl.Utf8,  # ST/*ST 类型名称
    "list_status": pl.Utf8,  # L正常/D退市/P暂停
    "source": pl.Utf8,
    "src_code": pl.Utf8,
}


# ============================================================
# Tushare Source Schemas (for empty DataFrame creation)
# ============================================================
# These schemas are used in Tushare source methods to create empty DataFrames
# when API calls fail. They define the minimal structure for temporary DataFrames.


# ST (Special Treatment) stock schema
# Used in TushareSource._fetch_st_data() for stock_st API
TUSHARE_ST_SCHEMA: dict[str, type[pl.DataType]] = {
    "ts_code": pl.String,
    "name": pl.String,
}


# List status schema
# Used in TushareSource._fetch_list_status_data() for stock_basic API
TUSHARE_LIST_STATUS_SCHEMA: dict[str, type[pl.DataType]] = {
    "ts_code": pl.String,
    "list_status": pl.String,
}
