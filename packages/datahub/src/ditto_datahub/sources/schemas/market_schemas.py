"""
Market SourceSchema definitions.

定义 Market 域的 SourceSchema，作为数据源输出的标准协议。

Market 域数据类型：
1. Stock Daily (股票日线) - 带 knowledge_date
2. ETF Daily (ETF 日线) - 带 knowledge_date
3. Adj Factor (复权因子) - 带 knowledge_date
4. Stock Status (股票状态) - 允许重复主键
5. Stock Limit (涨跌停价)
6. Fund Adj (基金复权因子) - 带 knowledge_date
"""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = [
    "ADJ_FACTOR_SOURCE_SCHEMA",
    "ETF_DAILY_SOURCE_SCHEMA",
    "FUND_ADJ_SOURCE_SCHEMA",
    "STOCK_DAILY_SOURCE_SCHEMA",
    "STOCK_LIMIT_SOURCE_SCHEMA",
    "STOCK_STATUS_SOURCE_SCHEMA",
]

# ============================================================================
# 1. 股票日线行情 (带 knowledge_date)
# ============================================================================

STOCK_DAILY_SOURCE_SCHEMA = SourceSchema(
    dataset="stock_daily",
    key_columns=("src_code", "trade_date"),
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
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

# ============================================================================
# 2. ETF 日线行情 (带 knowledge_date)
# ============================================================================

ETF_DAILY_SOURCE_SCHEMA = SourceSchema(
    dataset="etf_daily",
    key_columns=("src_code", "trade_date"),
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
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

# ============================================================================
# 3. 复权因子 (带 knowledge_date)
# ============================================================================

ADJ_FACTOR_SOURCE_SCHEMA = SourceSchema(
    dataset="adj_factor",
    key_columns=("src_code", "trade_date"),
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "adj_factor": pl.Float64,
    },
)

# ============================================================================
# 4. 股票状态 (允许重复主键 - 同一股票同一天多条状态记录)
# ============================================================================

STOCK_STATUS_SOURCE_SCHEMA = SourceSchema(
    dataset="stock_status",
    key_columns=(),  # 空主键，不验证唯一性
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
        "is_suspended": pl.Boolean,
        "suspend_timing": pl.String,
        "is_st": pl.Boolean,
        "st_type": pl.String,
        "list_status": pl.String,
    },
)

# ============================================================================
# 5. 涨跌停价
# ============================================================================

STOCK_LIMIT_SOURCE_SCHEMA = SourceSchema(
    dataset="stock_limit",
    key_columns=("src_code", "trade_date"),
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
        "up_limit": pl.Float64,
        "down_limit": pl.Float64,
    },
)

# ============================================================================
# 6. 基金复权因子 (带 knowledge_date)
# ============================================================================

FUND_ADJ_SOURCE_SCHEMA = SourceSchema(
    dataset="fund_adj",
    key_columns=("src_code", "trade_date"),
    schema={
        "src_code": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "adj_factor": pl.Float64,
    },
)
