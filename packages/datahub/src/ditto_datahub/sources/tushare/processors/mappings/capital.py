"""资本域 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_datahub.sources.tushare.processors.column_mapping import ColumnMapping

# Valuation Metrics (PE/PB) - PIT data
VALUATION_METRICS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "pe": "pe_ratio",
        "pb": "pb_ratio",
        "ps": "ps_ratio",
        "dv_ratio": "dividend_yield",
        "total_mv": "market_cap",
    },
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"],
    computed_columns={"knowledge_date": pl.col("trade_date") + pl.duration(days=1)},
    output_columns=(
        "source_ticker",
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
# P015 修复：添加 div_proc 字段区分预案/实施
# Note: dividend_yield is not available from Tushare dividend API.
# It's computed from valuation_metrics dv_ratio field separately.
# We include it as null to satisfy the schema contract.
DIVIDEND_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ex_date": "ex_dividend_date",
        "cash_div": "dividend_per_share",
        "ann_date": "knowledge_date",
        "div_proc": "div_proc",  # P015: 添加实施进度字段
    },
    date_columns={"ex_dividend_date": "%Y%m%d", "knowledge_date": "%Y%m%d"},
    float_columns=["dividend_per_share"],
    computed_columns={
        "dividend_yield": pl.lit(None, dtype=pl.Float64),
    },
    output_columns=(
        "source_ticker",
        "ex_dividend_date",
        "knowledge_date",
        "dividend_per_share",
        "dividend_yield",
        "div_proc",  # P015: 输出包含实施进度
    ),
)

# Margin Trading - PIT data
MARGIN_TRADING_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "rzye": "margin_buy_balance",
        "rqye": "short_sell_balance",
        "rzmre": "margin_buy_volume",
        "rqmcl": "short_sell_volume",
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
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ),
)

# Pledge Ratio - PIT data
# Note: Tushare pledge_stat API returns end_date as report date
PLEDGE_RATIO_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "end_date": "report_date",
        "total_share": "total_shares",
    },
    date_columns={"report_date": "%Y%m%d"},
    float_columns=["pledge_ratio", "total_shares"],
    computed_columns={"knowledge_date": pl.col("report_date")},
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "pledge_ratio",
        "total_shares",
    ),
)

# Index Composition - PIT data
# out_date 为成分退出日期，映射为 effective_to（NULL 表示当前成分）
INDEX_COMPOSITION_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker", "index_code": "index_id"},
    date_columns={"in_date": "%Y%m%d", "out_date": "%Y%m%d"},
    float_columns=["weight"],
    int_columns=("is_new",),
    computed_columns={
        "effective_from": pl.col("in_date"),
        "effective_to": pl.col("out_date"),
    },
    output_columns=(
        "index_id",
        "source_ticker",
        "weight",
        "effective_from",
        "effective_to",
    ),
)

# Corporate Actions - Non-PIT data
CORPORATE_ACTIONS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ba_type": "action_type",
        "ann_date": "announcement_date",
        "act_date": "effective_date",
        "name": "description",
    },
    date_columns={"announcement_date": "%Y%m%d", "effective_date": "%Y%m%d"},
    float_columns=[],
    output_columns=(
        "source_ticker",
        "action_type",
        "announcement_date",
        "effective_date",
        "description",
    ),
)

# Balance Sheet - PIT data (simplified fields)
BALANCE_SHEET_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "total_liab": "total_liabilities",
    },
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_assets",
        "total_liabilities",  # After rename
        "total_hldr_eqy_exc_min_int",
        "total_cur_assets",
        "total_cur_liab",
        "inventory",
        "fixed_assets",
        "cash_equivalents",
        "accounts_receivable",
        "short_term_debt",
        "long_term_debt",
        "money_cap",
        "total_share",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "net_assets": pl.col("total_hldr_eqy_exc_min_int"),
        "current_assets": pl.col("total_cur_assets"),
        "current_liabilities": pl.col("total_cur_liab"),
    },
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "total_assets",
        "total_liabilities",
        "net_assets",
        "current_assets",
        "current_liabilities",
        "inventory",
        "fixed_assets",
        "cash_equivalents",
        "accounts_receivable",
        "short_term_debt",
        "long_term_debt",
        "money_cap",
        "total_share",
    ),
)

# Income Statement - PIT data (simplified fields)
# Note: Tushare API fields are: total_revenue, operate_profit, n_income, basic_eps
INCOME_STATEMENT_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "total_revenue",
        "operate_cost",
        "sale_exp",
        "admin_exp",
        "fin_exp",
        "rd_exp",
        "operate_profit",
        "total_profit",
        "income_tax",
        "n_income",
        "basic_eps",
        "diluted_eps",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("ann_date"),
        "revenue": pl.col("total_revenue"),
        "operating_profit": pl.col("operate_profit"),
        "net_profit": pl.col("n_income"),
        "eps": pl.col("basic_eps"),
    },
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "revenue",
        "operating_profit",
        "net_profit",
        "eps",
        "operate_cost",
        "sale_exp",
        "admin_exp",
        "fin_exp",
        "rd_exp",
        "total_profit",
        "income_tax",
        "diluted_eps",
    ),
)

# Cash Flow - PIT data (simplified fields)
CASH_FLOW_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"end_date": "%Y%m%d", "ann_date": "%Y%m%d"},
    float_columns=[
        "n_cashflow_act",
        "n_cash_flows_inv_act",
        "n_cash_flows_fnc_act",
        "depreciation",
        "interest_paid",
        "tax_paid",
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
        "source_ticker",
        "report_date",
        "knowledge_date",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
        "depreciation",
        "interest_paid",
        "tax_paid",
    ),
)

__all__ = [
    "BALANCE_SHEET_MAPPING",
    "CASH_FLOW_MAPPING",
    "CORPORATE_ACTIONS_MAPPING",
    "DIVIDEND_MAPPING",
    "INCOME_STATEMENT_MAPPING",
    "INDEX_COMPOSITION_MAPPING",
    "MARGIN_TRADING_MAPPING",
    "PLEDGE_RATIO_MAPPING",
    "VALUATION_METRICS_MAPPING",
]
