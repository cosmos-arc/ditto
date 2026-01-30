"""
Capital SourceSchema definitions.

定义 Capital 域的 SourceSchema，作为数据源输出的标准协议。

Capital 域数据类型：
1. Balance Sheet (资产负债表) - PIT
2. Income Statement (利润表) - PIT
3. Cash Flow (现金流量表) - PIT
4. Valuation Metrics (估值指标) - PIT
5. Futures (期货衍生品) - PIT
6. Index Composition (指数成分股) - PIT
7. Corporate Actions (公司行为) - 非PIT
8. Dividend (股息分红) - PIT
9. Margin Trading (融资融券) - PIT
10. Pledge Ratio (股权质押) - PIT
"""

import polars as pl

from ditto_datahub.sources.source_schema import SourceSchema

__all__ = [
    "BALANCE_SHEET_SOURCE_SCHEMA",
    "CASH_FLOW_SOURCE_SCHEMA",
    "CORPORATE_ACTIONS_SOURCE_SCHEMA",
    "DIVIDEND_SOURCE_SCHEMA",
    "FUTURES_SOURCE_SCHEMA",
    "INCOME_STATEMENT_SOURCE_SCHEMA",
    "INDEX_COMPOSITION_SOURCE_SCHEMA",
    "MARGIN_TRADING_SOURCE_SCHEMA",
    "PLEDGE_RATIO_SOURCE_SCHEMA",
    "VALUATION_METRICS_SOURCE_SCHEMA",
]

# ============================================================================
# 1. 财务报表数据 (PIT)
# ============================================================================

BALANCE_SHEET_SOURCE_SCHEMA = SourceSchema(
    dataset="balance_sheet",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "total_assets": pl.Float64,
        "total_liabilities": pl.Float64,
        "net_assets": pl.Float64,
        "current_assets": pl.Float64,
        "current_liabilities": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

INCOME_STATEMENT_SOURCE_SCHEMA = SourceSchema(
    dataset="income_statement",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "revenue": pl.Float64,
        "operating_profit": pl.Float64,
        "net_profit": pl.Float64,
        "eps": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

CASH_FLOW_SOURCE_SCHEMA = SourceSchema(
    dataset="cash_flow",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "operating_cash_flow": pl.Float64,
        "investing_cash_flow": pl.Float64,
        "financing_cash_flow": pl.Float64,
        "net_cash_flow": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

# ============================================================================
# 2. 估值指标数据 (PIT)
# ============================================================================

VALUATION_METRICS_SOURCE_SCHEMA = SourceSchema(
    dataset="valuation_metrics",
    key_columns=("instrument_id", "trade_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "pe_ratio": pl.Float64,
        "pb_ratio": pl.Float64,
        "ps_ratio": pl.Float64,
        "dividend_yield": pl.Float64,
        "market_cap": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

# ============================================================================
# 3. 衍生品数据 (PIT)
# ============================================================================

FUTURES_SOURCE_SCHEMA = SourceSchema(
    dataset="futures",
    key_columns=("instrument_id", "trade_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "open_interest": pl.Float64,
        "settlement_price": pl.Float64,
        "volume": pl.Float64,
        "turnover": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

# ============================================================================
# 4. 成分股数据 (PIT)
# ============================================================================

INDEX_COMPOSITION_SOURCE_SCHEMA = SourceSchema(
    dataset="index_composition",
    key_columns=("index_id", "instrument_id", "effective_from"),
    schema={
        "index_id": pl.String,
        "instrument_id": pl.String,
        "weight": pl.Float64,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
    },
    pit_columns=("effective_from", "effective_to"),
)

DIVIDEND_SOURCE_SCHEMA = SourceSchema(
    dataset="dividend",
    key_columns=("instrument_id", "ex_dividend_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "ex_dividend_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "dividend_per_share": pl.Float64,
        "dividend_yield": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

MARGIN_TRADING_SOURCE_SCHEMA = SourceSchema(
    dataset="margin_trading",
    key_columns=("instrument_id", "trade_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "trade_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "margin_buy_balance": pl.Float64,
        "short_sell_balance": pl.Float64,
        "margin_buy_volume": pl.Float64,
        "short_sell_volume": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

PLEDGE_RATIO_SOURCE_SCHEMA = SourceSchema(
    dataset="pledge_ratio",
    key_columns=("instrument_id", "report_date", "effective_from"),
    schema={
        "instrument_id": pl.String,
        "report_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "pledge_ratio": pl.Float64,
        "pledge_shares": pl.Float64,
        "total_shares": pl.Float64,
    },
    pit_columns=("effective_from", "effective_to"),
)

# ============================================================================
# 5. 公司行为 (非 PIT)
# ============================================================================

CORPORATE_ACTIONS_SOURCE_SCHEMA = SourceSchema(
    dataset="corporate_actions",
    key_columns=("instrument_id", "action_type", "announcement_date"),
    schema={
        "instrument_id": pl.String,
        "action_type": pl.String,
        "announcement_date": pl.Date,
        "effective_date": pl.Date,
        "description": pl.String,
    },
    pit_columns=(),
)
