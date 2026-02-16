"""资本域 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.tushare.processors.column_mapping import ColumnMapping

# Valuation Metrics (PE/PB) - PIT data
VALUATION_METRICS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "pe": "pe_ratio",
        "pb": "pb_ratio",
        "ps": "ps_ratio",
        "total_mv": "market_cap",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "pe_ratio",
        "pb_ratio",
        "ps_ratio",
        "dividend_yield",
        "market_cap",
    ),
)

# Dividend - PIT data
DIVIDEND_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "ex_date": "ex_dividend_date",
        "dividend": "dividend_per_share",
    },
    date_columns={"ex_dividend_date": "%Y%m%d"},
    float_columns=["dividend_per_share", "dividend_yield"],
    computed_columns={
        "knowledge_date": pl.col("ex_dividend_date") + pl.duration(days=1)
    },
    output_columns=(
        "instrument_id",
        "ex_dividend_date",
        "knowledge_date",
        "dividend_per_share",
        "dividend_yield",
    ),
)

# Margin Trading - PIT data
MARGIN_TRADING_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "rz_balance": "margin_buy_balance",
        "rz_vol": "margin_buy_volume",
        "rq_balance": "short_sell_balance",
        "rq_vol": "short_sell_volume",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ),
)

# Pledge Ratio - PIT data
# Note: Tushare pledge API does not return report_date, we'll add it in the method
PLEDGE_RATIO_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "pledge_count": "pledge_shares",
        "total_share": "total_shares",
    },
    date_columns={},
    float_columns=["pledge_ratio", "pledge_shares", "total_shares"],
    computed_columns={},
    output_columns=(
        "instrument_id",
        "pledge_ratio",
        "pledge_shares",
        "total_shares",
    ),
)

# Futures - PIT data
FUTURES_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "oi": "open_interest",
        "settlement": "settlement_price",
        "vol": "volume",
        "amount": "turnover",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["open_interest", "settlement_price", "volume", "turnover"],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "instrument_id",
        "trade_date",
        "knowledge_date",
        "open_interest",
        "settlement_price",
        "volume",
        "turnover",
    ),
)

# Index Composition - PIT data
INDEX_COMPOSITION_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id", "index_code": "index_id"},
    date_columns={"in_date": "%Y%m%d"},
    float_columns=["weight"],
    int_columns=("is_new",),
    computed_columns={"effective_from": pl.col("in_date")},
    output_columns=(
        "index_id",
        "instrument_id",
        "weight",
        "effective_from",
    ),
)

# Corporate Actions - Non-PIT data
CORPORATE_ACTIONS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "ba_type": "action_type",
        "ann_date": "announcement_date",
        "act_date": "effective_date",
        "name": "description",
    },
    date_columns={"announcement_date": "%Y%m%d", "effective_date": "%Y%m%d"},
    float_columns=[],
    output_columns=(
        "instrument_id",
        "action_type",
        "announcement_date",
        "effective_date",
        "description",
    ),
)

# Balance Sheet - PIT data (simplified fields)
BALANCE_SHEET_MAPPING = ColumnMapping(
    rename={
        "ts_code": "instrument_id",
        "total_liab": "total_liabilities",
    },
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_assets",
        "total_liabilities",  # After rename
        "total_hldr_eqy_exc_min_int",
        "total_cur_assets",
        "total_cur_liab",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "net_assets": pl.col("total_hldr_eqy_exc_min_int"),
        "current_assets": pl.col("total_cur_assets"),
        "current_liabilities": pl.col("total_cur_liab"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "total_assets",
        "total_liabilities",
        "net_assets",
        "current_assets",
        "current_liabilities",
    ),
)

# Income Statement - PIT data (simplified fields)
INCOME_STATEMENT_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_operating_revenue",
        "operating_profit",
        "net_profit",
        "basic_eps",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "revenue": pl.col("total_operating_revenue"),
        "eps": pl.col("basic_eps"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "revenue",
        "operating_profit",
        "net_profit",
        "eps",
    ),
)

# Cash Flow - PIT data (simplified fields)
CASH_FLOW_MAPPING = ColumnMapping(
    rename={"ts_code": "instrument_id"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "n_cashflow_act",
        "n_cash_flows_inv_act",
        "n_cash_flows_fnc_act",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "operating_cash_flow": pl.col("n_cashflow_act"),
        "investing_cash_flow": pl.col("n_cash_flows_inv_act"),
        "financing_cash_flow": pl.col("n_cash_flows_fnc_act"),
        "net_cash_flow": pl.col("n_cashflow_act")
        + pl.col("n_cash_flows_inv_act")
        + pl.col("n_cash_flows_fnc_act"),
    },
    output_columns=(
        "instrument_id",
        "report_date",
        "knowledge_date",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
    ),
)

__all__ = [
    "BALANCE_SHEET_MAPPING",
    "CASH_FLOW_MAPPING",
    "CORPORATE_ACTIONS_MAPPING",
    "DIVIDEND_MAPPING",
    "FUTURES_MAPPING",
    "INCOME_STATEMENT_MAPPING",
    "INDEX_COMPOSITION_MAPPING",
    "MARGIN_TRADING_MAPPING",
    "PLEDGE_RATIO_MAPPING",
    "VALUATION_METRICS_MAPPING",
]
