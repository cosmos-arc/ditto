"""资本域 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.processors.column_mapping import ColumnMapping

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
# Note: Tushare pledge_stat API returns end_date as report date.
# PIT 语义：knowledge_date = report_date，即质押比率的"知晓日期"等于报告期本身
# （非公告日）。这与财报类数据使用 ann_date 作为 knowledge_date 不同。
# 原因：Tushare pledge_stat API 不提供 ann_date 字段，end_date 是唯一可用的时间锚点。
# 消费方应按 knowledge_date 进行 PIT 查询，确保 T 日只能看到 report_date <= T 的记录。
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

# Corporate Actions - PIT data
CORPORATE_ACTIONS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ba_type": "action_type",
        "ann_date": "action_date",
        "act_date": "effective_from",
        "name": "description",
    },
    date_columns={"action_date": "%Y%m%d", "effective_from": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "knowledge_date": pl.col("action_date"),
        "effective_to": pl.lit(None, dtype=pl.Date),
    },
    output_columns=(
        "source_ticker",
        "action_type",
        "action_date",
        "knowledge_date",
        "effective_from",
        "effective_to",
        "description",
    ),
)

# Balance Sheet - PIT data (simplified fields)
# 披露锚 = f_ann_date（实际公告日，ADR 红线 4）
BALANCE_SHEET_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "total_liab": "total_liabilities",
    },
    date_columns={"end_date": "%Y%m%d", "f_ann_date": "%Y%m%d"},
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
        "knowledge_date": pl.col("f_ann_date"),
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
    date_columns={"end_date": "%Y%m%d", "f_ann_date": "%Y%m%d"},
    float_columns=[
        "total_revenue",
        "revenue",
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
        "knowledge_date": pl.col("f_ann_date"),
        "revenue": pl.col("total_revenue"),
        "operating_revenue": pl.col("revenue"),
        "operating_profit": pl.col("operate_profit"),
        "net_profit": pl.col("n_income"),
        "eps": pl.col("basic_eps"),
    },
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "revenue",
        "operating_revenue",
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
    date_columns={"end_date": "%Y%m%d", "f_ann_date": "%Y%m%d"},
    float_columns=[
        "n_cashflow_act",
        "n_cashflow_inv_act",
        "n_cashflow_fnc_act",
    ],
    computed_columns={
        "report_date": pl.col("end_date"),
        "knowledge_date": pl.col("f_ann_date"),
        "operating_cash_flow": pl.col("n_cashflow_act"),
        "investing_cash_flow": pl.col("n_cashflow_inv_act"),
        "financing_cash_flow": pl.col("n_cashflow_fnc_act"),
        "net_cash_flow": pl.col("n_cashflow_act")
        + pl.col("n_cashflow_inv_act")
        + pl.col("n_cashflow_fnc_act"),
    },
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
    ),
)

# Share Buyback (限售解禁) - Non-PIT data
SHARE_BUYBACK_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ann_date": "announcement_date",
        "float_date": "effective_date",
        "float_share": "float_shares",
    },
    date_columns={"announcement_date": "%Y%m%d", "effective_date": "%Y%m%d"},
    float_columns=["float_shares", "float_ratio"],
    output_columns=(
        "source_ticker",
        "announcement_date",
        "effective_date",
        "float_shares",
        "float_ratio",
    ),
)

# Rights Issue (配股) - Non-PIT data
RIGHTS_ISSUE_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ann_date": "announcement_date",
        "reg_date": "record_date",
        "ex_date": "ex_rights_date",
    },
    date_columns={
        "announcement_date": "%Y%m%d",
        "record_date": "%Y%m%d",
        "ex_rights_date": "%Y%m%d",
    },
    float_columns=["rights_price", "rights_ratio"],
    output_columns=(
        "source_ticker",
        "rights_type",
        "announcement_date",
        "record_date",
        "ex_rights_date",
        "rights_price",
        "rights_ratio",
    ),
)

# ---------------------------------------------------------------------------
# #518/#519/#520/#521/#522 资金面/情绪/席位/财务指标/基金持仓增补
# 单位口径登记（#506 坑 F，2026-10-06 代理实测）：
# - moneyflow：金额字段全部**万元**、量字段全部**手**（buy/sell_elg|lg|md|sm_*
#   与 net_mf_*，net=买入-卖出）；
# - cyq_perf：cost_5/15/50/85/95pct、his_high/low、weight_avg 单位**元**，
#   winner_rate 为 **%**；
# - hk_hold：vol 单位**股**、ratio **%**（2024-08 披露改制后北向仅季度末披露）；
# - hsgt_top10：amount/buy/sell/net_amount 单位**元**，改制后 buy/sell/
#   net_amount 官方停披（null 保留，不得填零）；
# - top_list/top_inst：金额**元**、比率 **%**，side '0'=买 '1'=卖；
# - fina_indicator：每股指标**元/股**、比率 **%**、绝对额**元**，118 列透传；
# - fund_portfolio：market_value(mkv) **元**、holding_shares(amount) **股**、
#   比率 **%**；fund_share fd_share 单位**万份**（见 common.py）。
# 日频数据集 kd=T+1 对齐日行情口径；披露锚数据集（fina_indicator/
# fund_portfolio）kd=公告日。
# ---------------------------------------------------------------------------

# 个股资金流向（moneyflow，金额万元/量手）
MONEYFLOW_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "buy_elg_amount",
        "buy_elg_vol",
        "buy_lg_amount",
        "buy_lg_vol",
        "buy_md_amount",
        "buy_md_vol",
        "buy_sm_amount",
        "buy_sm_vol",
        "sell_elg_amount",
        "sell_elg_vol",
        "sell_lg_amount",
        "sell_lg_vol",
        "sell_md_amount",
        "sell_md_vol",
        "sell_sm_amount",
        "sell_sm_vol",
        "net_mf_amount",
        "net_mf_vol",
    ],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "buy_elg_amount",
        "buy_elg_vol",
        "buy_lg_amount",
        "buy_lg_vol",
        "buy_md_amount",
        "buy_md_vol",
        "buy_sm_amount",
        "buy_sm_vol",
        "sell_elg_amount",
        "sell_elg_vol",
        "sell_lg_amount",
        "sell_lg_vol",
        "sell_md_amount",
        "sell_md_vol",
        "sell_sm_amount",
        "sell_sm_vol",
        "net_mf_amount",
        "net_mf_vol",
    ),
)

# 每日筹码及胜率（cyq_perf，价格类元、winner_rate %）
CYQ_PERF_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "cost_5pct",
        "cost_15pct",
        "cost_50pct",
        "cost_85pct",
        "cost_95pct",
        "his_high",
        "his_low",
        "weight_avg",
        "winner_rate",
    ],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "cost_5pct",
        "cost_15pct",
        "cost_50pct",
        "cost_85pct",
        "cost_95pct",
        "his_high",
        "his_low",
        "weight_avg",
        "winner_rate",
    ),
)

# 沪深港通持股（hk_hold：北向 SH/SZ 行入库，南向 HK 行在身份富集处过滤）
HK_HOLD_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["vol", "ratio"],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "vol",
        "ratio",
        "exchange",
    ),
)

# 沪深港通十大成交股（hsgt_top10：改制后 buy/sell/net_amount 停披为 null）
HSGT_TOP10_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker", "change": "pct_change"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "close",
        "pct_change",
        "amount",
        "net_amount",
        "buy",
        "sell",
    ],
    int_columns=("rank",),
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "close",
        "pct_change",
        "rank",
        "market_type",
        "amount",
        "net_amount",
        "buy",
        "sell",
    ),
)

# 龙虎榜个股（top_list：同标的同日可因多个上榜原因出现多行，reason 进主键）
TOP_LIST_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=[
        "close",
        "pct_change",
        "turnover_rate",
        "amount",
        "l_sell",
        "l_buy",
        "l_amount",
        "net_amount",
        "net_rate",
        "amount_rate",
        "float_values",
    ],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "name",
        "close",
        "pct_change",
        "turnover_rate",
        "amount",
        "l_sell",
        "l_buy",
        "l_amount",
        "net_amount",
        "net_rate",
        "amount_rate",
        "float_values",
        "reason",
    ),
)

# 龙虎榜席位明细（top_inst：side '0'=买 '1'=卖，exalter=席位名称）
TOP_INST_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["buy", "buy_rate", "sell", "sell_rate", "net_buy"],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "exalter",
        "side",
        "buy",
        "buy_rate",
        "sell",
        "sell_rate",
        "net_buy",
        "reason",
    ),
)

# 官方口径财务指标（fina_indicator：118 指标列透传，kd=公告日 ann_date）
FINA_INDICATOR_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ann_date": "knowledge_date",
        "end_date": "report_date",
    },
    date_columns={
        "knowledge_date": "%Y%m%d",
        "report_date": "%Y%m%d",
    },
    float_columns=[],
    output_columns=None,
)

# 基金持仓（fund_portfolio：公告日驱动，holding_symbol=持仓股票代码）
FUND_PORTFOLIO_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ann_date": "knowledge_date",
        "end_date": "report_date",
        "symbol": "holding_symbol",
        "mkv": "market_value",
        "amount": "holding_shares",
    },
    date_columns={
        "knowledge_date": "%Y%m%d",
        "report_date": "%Y%m%d",
    },
    float_columns=[
        "market_value",
        "holding_shares",
        "stk_mkv_ratio",
        "stk_float_ratio",
    ],
    output_columns=(
        "source_ticker",
        "report_date",
        "knowledge_date",
        "holding_symbol",
        "market_value",
        "holding_shares",
        "stk_mkv_ratio",
        "stk_float_ratio",
    ),
)

__all__ = [
    "BALANCE_SHEET_MAPPING",
    "CASH_FLOW_MAPPING",
    "CORPORATE_ACTIONS_MAPPING",
    "CYQ_PERF_MAPPING",
    "DIVIDEND_MAPPING",
    "FINA_INDICATOR_MAPPING",
    "FUND_PORTFOLIO_MAPPING",
    "HK_HOLD_MAPPING",
    "HSGT_TOP10_MAPPING",
    "INCOME_STATEMENT_MAPPING",
    "INDEX_COMPOSITION_MAPPING",
    "MARGIN_TRADING_MAPPING",
    "MONEYFLOW_MAPPING",
    "PLEDGE_RATIO_MAPPING",
    "RIGHTS_ISSUE_MAPPING",
    "SHARE_BUYBACK_MAPPING",
    "TOP_INST_MAPPING",
    "TOP_LIST_MAPPING",
    "VALUATION_METRICS_MAPPING",
]
