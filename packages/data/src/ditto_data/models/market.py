"""
Market 域数据模型（Schema 定义）.

本模块定义 Market 域的数据密集型模型，使用 Polars Schema 表示。

设计原则:
- 数据密集型用 Schema（DataFrame 传输）
- 支持向量化计算
- 类型安全（Polars 类型系统）
"""

import polars as pl

# 标准 K线 Schema
BAR_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}

# 增强 K线 Schema（含涨跌幅）
BAR_ENRICHED_SCHEMA: dict[str, type[pl.DataType]] = {
    **BAR_SCHEMA,
    "pct_change": pl.Float64,
    "turnover": pl.Float64,
}

# 报价 Schema
QUOTE_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,
    "trade_time": pl.Time,
    "price": pl.Float64,
    "volume": pl.Float64,
    "bid1": pl.Float64,
    "ask1": pl.Float64,
    "bid1_volume": pl.Float64,
    "ask1_volume": pl.Float64,
}

__all__ = [
    "BAR_ENRICHED_SCHEMA",
    "BAR_SCHEMA",
    "QUOTE_SCHEMA",
]
