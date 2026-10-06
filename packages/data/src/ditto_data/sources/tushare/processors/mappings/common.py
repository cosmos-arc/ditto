"""通用 ColumnMapping 定义."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.tushare.processors.column_mapping import ColumnMapping

# OHLCV 数据的通用配置
# knowledge_date = trade_date + 1（日行情数据 T+1 可知）
#
# 单位合同（#506 坑 B 组，#507 B1）：Tushare daily/fund_daily/index_daily 的
# vol 单位为手、amount 单位为千元，原值入库不做换算——这是全仓库的操作口径
# （fuyao 对账在源侧归一为手/千元，见 config/default/dq_rules/stock_daily.yml
# 与 index_daily.yml 的换算系数）。消费方比较或换算时以本注释为准；
# daily_basic.total_mv（万元）、index_dailybasic（元/股）等其他端点单位不同，
# 见各自 mapping 注释，不得跨端点套用。
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

# #483 ETF 单位净值：nav_date（估值日）即交易日列；knowledge_date 用 ann_date
# （披露锚，QDII 可晚于估值日；未知披露日保留 nullable Date）
ETF_NAV_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker"},
    date_columns={"ann_date": "%Y%m%d", "nav_date": "%Y%m%d"},
    float_columns=["unit_nav", "acc_nav"],
    computed_columns={
        "trade_date": pl.col("nav_date"),
        "knowledge_date": pl.col("ann_date"),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "unit_nav",
        "acc_nav",
    ),
)

# #522 基金份额（fund_share）：ETF 逐日申报（OF 基金节奏不定），
# fd_share 单位**万份**；market 为交易所（SH/SZ），kd=T+1。
# fund_type 显式 String cast：透传列全 null 批次 JSON 推断 Null dtype，
# 会被 #529 复活的 type_check(string) 误阻断（合法可选列）。
FUND_SHARE_MAPPING = ColumnMapping(
    rename={"ts_code": "source_ticker", "market": "exchange"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["fd_share"],
    computed_columns={
        "knowledge_date": pl.col("trade_date") + pl.duration(days=1),
        "fund_type": pl.col("fund_type").cast(pl.String, strict=False),
    },
    output_columns=(
        "source_ticker",
        "trade_date",
        "knowledge_date",
        "fd_share",
        "fund_type",
        "exchange",
    ),
)

__all__ = [
    "ADJ_FACTOR_MAPPING",
    "CALENDAR_MAPPING",
    "DAILY_OHLCV_MAPPING",
    "ETF_NAV_MAPPING",
    "FUND_ADJ_MAPPING",
    "FUND_SHARE_MAPPING",
]
