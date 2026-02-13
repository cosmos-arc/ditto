"""通用 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.tushare.processors.column_mapping import ColumnMapping

# OHLCV 数据的通用配置
# knowledge_date = trade_date + 1（日行情数据 T+1 可知）
DAILY_OHLCV_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker", "vol": "volume", "pct_chg": "pct_change"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "pct_change",
    ],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "pct_change",
    ),
)

# 交易日历配置
CALENDAR_MAPPING = ColumnMapping(
    rename={"cal_date": "trade_date"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[],
    boolean_columns=("is_open",),
    output_columns=("trade_date", "is_open"),
)

# 复权因子配置（股票）
# knowledge_date = trade_date（数据即日可用，直接复制已转换的 Date 列）
ADJ_FACTOR_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["adj_factor"],
    computed_columns={"knowledge_date": pl.col("trade_date")},
    output_columns=("source_ticker", "trade_date", "knowledge_date", "adj_factor"),
)

# 复权因子配置（ETF/基金）- 与股票复权因子结构相同
FUND_ADJ_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["adj_factor"],
    computed_columns={"knowledge_date": pl.col("trade_date")},
    output_columns=("source_ticker", "trade_date", "knowledge_date", "adj_factor"),
)

__all__ = [
    "ADJ_FACTOR_MAPPING",
    "CALENDAR_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "FUND_ADJ_MAPPING",
]
