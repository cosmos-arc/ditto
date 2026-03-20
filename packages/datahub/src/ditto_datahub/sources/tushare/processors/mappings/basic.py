"""基本信息 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.tushare.processors.column_mapping import ColumnMapping

# ETF 基本信息配置
# list_date 可能为空，后续通过行情数据推断
ETF_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "ticker": pl.col("source_ticker").str.split(".").list.get(0),
        "exchange": pl.col("source_ticker")
        .str.split(".")
        .list.get(1)
        .replace({"SH": "SSE", "SZ": "SZSE"}),
    },
    output_columns=("source_ticker", "ticker", "name", "exchange", "list_date"),
)

# 指数基本信息配置
# list_date 可能为空，后续通过行情数据推断
INDEX_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "ticker": pl.col("source_ticker").str.split(".").list.get(0),
        "exchange": pl.col("source_ticker")
        .str.split(".")
        .list.get(1)
        .replace({"SH": "SSE", "SZ": "SZSE"}),
    },
    output_columns=("source_ticker", "ticker", "name", "exchange", "list_date"),
)

# 股票基本信息配置
# list_status: L=正常上市, D=退市, P=暂停上市
STOCK_BASIC_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"list_date": "%Y%m%d", "delist_date": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "ticker": pl.col("source_ticker").str.split(".").list.get(0),
    },
    output_columns=(
        "source_ticker",
        "ticker",
        "name",
        "exchange",
        "list_date",
        "delist_date",
        "list_status",
    ),
)

# 涨跌停价格配置
STOCK_LIMIT_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["up_limit", "down_limit"],
    output_columns=("source_ticker", "trade_date", "up_limit", "down_limit"),
)

__all__ = [
    "ETF_BASIC_MAPPING",
    "INDEX_BASIC_MAPPING",
    "STOCK_BASIC_MAPPING",
    "STOCK_LIMIT_MAPPING",
]
