"""
Dataset configuration registry and query functions.

Contains the INGESTION_SPECS registry and all lookup/query functions
for accessing dataset configurations by tier, value, or dependency level.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import time

from ditto_data.errors import DatasetNotFoundError
from ditto_data.models import Dataset as _Dataset

from ditto_application.config.specs import (
    DatasetRef,
    DatasetSpec,
    TaskTier,
    create_t0_config,
    create_t1_config,
)

__all__ = [
    "INGESTION_SPECS",
    "get_all_datasets",
    "get_dataset_config",
    "get_dataset_config_by_value",
    "get_datasets_by_tier",
    "get_parallel_datasets",
]

# ============ Ingestion Specs ============
# 当前固定摄取配置。DataCatalog runtime 实现后将成为唯一真相源。

INGESTION_SPECS: dict[_Dataset, DatasetSpec] = {
    # T0: Meta datasets
    _Dataset.CALENDAR: create_t0_config(
        dataset=_Dataset.CALENDAR,
        description="交易日历",
        typical_available_time=time(8, 0),
        critical_fields=["cal_date", "is_trade"],
        task_name="ingest_calendar",
        timeout_seconds=60,
    ),
    _Dataset.STOCK_BASIC: create_t0_config(
        dataset=_Dataset.STOCK_BASIC,
        description="股票基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "symbol", "name", "market", "list_date"],
        task_name="ingest_stock_basic",
    ),
    _Dataset.ETF_BASIC: create_t0_config(
        dataset=_Dataset.ETF_BASIC,
        description="ETF基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "symbol", "name", "list_date"],
        task_name="ingest_etf_basic",
    ),
    _Dataset.INDEX_BASIC: create_t0_config(
        dataset=_Dataset.INDEX_BASIC,
        description="指数基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "name", "market"],
        task_name="ingest_index_basic",
    ),
    # 维护者确认的 ETF 参考事实（#408）：声明文件驱动，source=config；
    # 在 tushare 源的默认调度中按 SOURCE_UNSUPPORTED 精确跳过。
    _Dataset.ETF_REFERENCE: create_t0_config(
        dataset=_Dataset.ETF_REFERENCE,
        description="维护者确认的ETF参考事实(config源)",
        typical_available_time=time(8, 30),
        critical_fields=["source_ticker", "field", "value", "effective_from"],
        task_name="ingest_etf_reference",
    ),
    # T1: Incremental datasets
    _Dataset.ETF_DAILY: create_t1_config(
        dataset=_Dataset.ETF_DAILY,
        description="ETF日行情数据",
        typical_available_time=time(18, 0),
        depends_on=[_Dataset.ETF_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        task_name="ingest_etf_bars",
    ),
    _Dataset.INDEX_DAILY: create_t1_config(
        dataset=_Dataset.INDEX_DAILY,
        description="指数日行情数据",
        typical_available_time=time(18, 0),
        depends_on=[_Dataset.INDEX_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        task_name="ingest_index_daily",
        priority=15,
    ),
    _Dataset.GLOBAL_INDEX_DAILY: create_t1_config(
        dataset=_Dataset.GLOBAL_INDEX_DAILY,
        description="全球核心指数日行情数据",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=[
            "source_ticker",
            "trade_date",
            "event_time",
            "close",
            "knowledge_date",
        ],
        task_name="ingest_global_index_daily",
        priority=16,
    ),
    _Dataset.STOCK_DAILY: create_t1_config(
        dataset=_Dataset.STOCK_DAILY,
        description="股票日行情数据",
        typical_available_time=time(17, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
        task_name="ingest_stock_daily",
        timeout_seconds=600,
    ),
    _Dataset.STOCK_STATUS: create_t1_config(
        dataset=_Dataset.STOCK_STATUS,
        description="股票状态数据",
        typical_available_time=time(17, 30),
        depends_on=[_Dataset.STOCK_DAILY],
        critical_fields=[
            "trade_date",
            "source_ticker",
            "is_suspended",
            "is_st",
            "list_status",
        ],
        task_name="ingest_stock_status",
        priority=25,
    ),
    _Dataset.ADJ_FACTOR: create_t1_config(
        dataset=_Dataset.ADJ_FACTOR,
        description="复权因子",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.STOCK_DAILY],
        critical_fields=["trade_date", "ts_code", "adj_factor"],
        task_name="ingest_adj_factor",
        priority=30,
    ),
    _Dataset.FUND_ADJ: create_t1_config(
        dataset=_Dataset.FUND_ADJ,
        description="ETF/基金复权因子",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.ETF_DAILY],
        critical_fields=["trade_date", "ts_code", "adj_factor"],
        task_name="ingest_fund_adj",
        priority=30,
    ),
    _Dataset.ETF_NAV: create_t1_config(
        dataset=_Dataset.ETF_NAV,
        description="ETF 单位净值",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.ETF_BASIC],
        critical_fields=["instrument_id", "trade_date", "unit_nav"],
        task_name="ingest_etf_nav",
        priority=31,
    ),
    # #517 涨跌停价格（stk_limit）：随日行情盘后可得
    _Dataset.STOCK_LIMIT: create_t1_config(
        dataset=_Dataset.STOCK_LIMIT,
        description="股票涨跌停价格",
        typical_available_time=time(17, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "up_limit", "down_limit"],
        task_name="ingest_stock_limit",
        priority=32,
    ),
    # #518 个股资金流向：唯一缺失的核心个股资金面因子
    _Dataset.MONEYFLOW: create_t1_config(
        dataset=_Dataset.MONEYFLOW,
        description="个股资金流向",
        typical_available_time=time(18, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "net_mf_amount"],
        task_name="ingest_moneyflow",
        priority=33,
    ),
    # #523 每日筹码及胜率（15000 档特色数据）
    _Dataset.CYQ_PERF: create_t1_config(
        dataset=_Dataset.CYQ_PERF,
        description="每日筹码及胜率",
        typical_available_time=time(18, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "winner_rate"],
        task_name="ingest_cyq_perf",
        priority=34,
    ),
    # #519 涨跌停/炸板名单（事件型：有上榜才有行）
    _Dataset.LIMIT_LIST: create_t1_config(
        dataset=_Dataset.LIMIT_LIST,
        description="涨跌停与炸板名单",
        typical_available_time=time(18, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "limit_type"],
        task_name="ingest_limit_list",
        priority=35,
    ),
    # #519 龙虎榜个股（事件型，reason 进主键）
    _Dataset.TOP_LIST: create_t1_config(
        dataset=_Dataset.TOP_LIST,
        description="龙虎榜个股明细",
        typical_available_time=time(18, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "reason", "l_buy"],
        task_name="ingest_top_list",
        priority=36,
    ),
    # #519 龙虎榜席位（事件型，exalter+side 进主键）
    _Dataset.TOP_INST: create_t1_config(
        dataset=_Dataset.TOP_INST,
        description="龙虎榜席位明细",
        typical_available_time=time(18, 30),
        depends_on=[_Dataset.TOP_LIST],
        critical_fields=["instrument_id", "trade_date", "exalter", "side"],
        task_name="ingest_top_inst",
        priority=37,
    ),
    # #520 北向持股（改制后北向季度末披露，南向过滤）
    _Dataset.HK_HOLD: create_t1_config(
        dataset=_Dataset.HK_HOLD,
        description="沪深港通持股(北向)",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "vol", "ratio"],
        task_name="ingest_hk_hold",
        priority=38,
    ),
    # #520 沪深港通十大成交股（改制后 buy/sell/net 停披）
    _Dataset.HSGT_TOP10: create_t1_config(
        dataset=_Dataset.HSGT_TOP10,
        description="沪深港通十大成交股",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "trade_date", "market_type", "amount"],
        task_name="ingest_hsgt_top10",
        priority=39,
    ),
    # #521 官方口径财务指标（披露增量语义对齐三表）
    _Dataset.FINA_INDICATOR: create_t1_config(
        dataset=_Dataset.FINA_INDICATOR,
        description="官方口径财务指标",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date", "roe"],
        task_name="ingest_fina_indicator",
        priority=40,
        timeout_seconds=900,
    ),
    # #522 基金份额（ETF 逐日申报）
    _Dataset.FUND_SHARE: create_t1_config(
        dataset=_Dataset.FUND_SHARE,
        description="基金份额",
        typical_available_time=time(21, 0),
        depends_on=[_Dataset.ETF_BASIC],
        critical_fields=["instrument_id", "trade_date", "fd_share"],
        task_name="ingest_fund_share",
        priority=41,
    ),
    # #522 基金季度持仓（公告日驱动）
    _Dataset.FUND_PORTFOLIO: create_t1_config(
        dataset=_Dataset.FUND_PORTFOLIO,
        description="基金季度持仓",
        typical_available_time=time(21, 0),
        depends_on=[_Dataset.ETF_BASIC],
        critical_fields=["instrument_id", "report_date", "holding_symbol"],
        task_name="ingest_fund_portfolio",
        priority=42,
    ),
    _Dataset.BALANCE_SHEET: create_t1_config(
        dataset=_Dataset.BALANCE_SHEET,
        description="资产负债表",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_balance_sheet",
        priority=35,
        timeout_seconds=900,
    ),
    _Dataset.INCOME_STATEMENT: create_t1_config(
        dataset=_Dataset.INCOME_STATEMENT,
        description="利润表",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_income_statement",
        priority=35,
        timeout_seconds=900,
    ),
    _Dataset.CASH_FLOW: create_t1_config(
        dataset=_Dataset.CASH_FLOW,
        description="现金流量表",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_cash_flow",
        priority=35,
        timeout_seconds=900,
    ),
    _Dataset.DIVIDEND: create_t1_config(
        dataset=_Dataset.DIVIDEND,
        description="分红送配数据",
        typical_available_time=time(20, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "ex_dividend_date", "knowledge_date"],
        task_name="ingest_dividend",
        priority=40,
    ),
    _Dataset.VALUATION_METRICS: create_t1_config(
        dataset=_Dataset.VALUATION_METRICS,
        description="估值指标",
        typical_available_time=time(19, 30),
        depends_on=[_Dataset.STOCK_DAILY],
        critical_fields=["instrument_id", "trade_date", "knowledge_date"],
        task_name="ingest_valuation_metrics",
        priority=45,
    ),
    _Dataset.MARGIN_TRADING: create_t1_config(
        dataset=_Dataset.MARGIN_TRADING,
        description="融资融券",
        typical_available_time=time(19, 30),
        depends_on=[_Dataset.STOCK_DAILY],
        critical_fields=["instrument_id", "trade_date", "knowledge_date"],
        task_name="ingest_margin_trading",
        priority=45,
    ),
    _Dataset.PLEDGE_RATIO: create_t1_config(
        dataset=_Dataset.PLEDGE_RATIO,
        description="股权质押",
        typical_available_time=time(21, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_pledge_ratio",
        priority=50,
    ),
    _Dataset.MACRO_INDICATORS: create_t1_config(
        dataset=_Dataset.MACRO_INDICATORS,
        description="宏观指标",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=["indicator_code", "date", "value"],
        task_name="ingest_macro_indicators",
        priority=55,
    ),
    _Dataset.FX_DAILY: create_t1_config(
        dataset=_Dataset.FX_DAILY,
        description="汇率日线数据",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=["instrument_id", "trade_date", "close"],
        task_name="ingest_fx_daily",
        priority=56,
    ),
    _Dataset.COMMODITY_DAILY: create_t1_config(
        dataset=_Dataset.COMMODITY_DAILY,
        description="商品价格数据",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=["instrument_id", "trade_date", "close"],
        task_name="ingest_commodity_daily",
        priority=57,
    ),
    _Dataset.CORPORATE_ACTIONS: create_t1_config(
        dataset=_Dataset.CORPORATE_ACTIONS,
        description="公司行为",
        typical_available_time=time(20, 0),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "action_type", "action_date"],
        task_name="ingest_corporate_actions",
        priority=65,
    ),
    _Dataset.INDEX_WEIGHT: create_t1_config(
        dataset=_Dataset.INDEX_WEIGHT,
        description="指数成分股权重",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.INDEX_BASIC],
        critical_fields=[
            "index_id",
            "instrument_id",
            "weight",
            "trade_date",
        ],
        task_name="ingest_index_weight",
        priority=50,
    ),
    _Dataset.INDUSTRY_CLASSIFICATION: create_t1_config(
        dataset=_Dataset.INDUSTRY_CLASSIFICATION,
        description="申万行业分类版本",
        typical_available_time=time(19, 0),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=[
            "source",
            "classification_version",
            "industry_id",
            "industry_name",
            "level",
            "knowledge_date",
        ],
        task_name="ingest_industry_classification",
        priority=11,
    ),
    _Dataset.INDUSTRY_MAPPING: create_t1_config(
        dataset=_Dataset.INDUSTRY_MAPPING,
        description="申万行业成分有效期映射",
        typical_available_time=time(19, 0),
        depends_on=[
            _Dataset.STOCK_BASIC,
            _Dataset.INDUSTRY_CLASSIFICATION,
        ],
        critical_fields=[
            "source",
            "classification_version",
            "instrument_id",
            "industry_id",
            "industry_date",
            "knowledge_date",
        ],
        task_name="ingest_industry_mapping",
        priority=12,
        timeout_seconds=900,
    ),
    _Dataset.NAME_CHANGE: create_t1_config(
        dataset=_Dataset.NAME_CHANGE,
        description="证券名称变更历史(可信历史事件流)",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=[
            "instrument_id",
            "new_name",
            "changed_date",
            "source",
            "observed_at",
        ],
        task_name="ingest_namechange",
        priority=13,
        timeout_seconds=900,
    ),
    _Dataset.ST_HISTORY: create_t1_config(
        dataset=_Dataset.ST_HISTORY,
        description="ST 状态变更历史(可信历史事件流)",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=[
            "instrument_id",
            "effective_from",
            "is_st",
            "source",
            "observed_at",
        ],
        task_name="ingest_st_history",
        priority=14,
        timeout_seconds=900,
    ),
    # #434 四组增补
    _Dataset.FUTURES_DAILY: create_t1_config(
        dataset=_Dataset.FUTURES_DAILY,
        description="国内期货合约日线",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=["source_ticker", "trade_date", "settle", "knowledge_date"],
        task_name="ingest_futures_daily",
        priority=58,
    ),
    _Dataset.FUTURES_BASIC: create_t1_config(
        dataset=_Dataset.FUTURES_BASIC,
        description="期货合约信息快照",
        typical_available_time=time(21, 30),
        depends_on=[_Dataset.CALENDAR],
        critical_fields=["source", "source_ticker", "knowledge_date"],
        task_name="ingest_futures_basic",
        priority=58,
    ),
    _Dataset.EARNINGS_FORECAST: create_t1_config(
        dataset=_Dataset.EARNINGS_FORECAST,
        description="业绩预告(净利润上下限万元)",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["source_ticker", "ann_date", "report_date", "forecast_type"],
        task_name="ingest_earnings_forecast",
        priority=60,
    ),
    _Dataset.EARNINGS_EXPRESS: create_t1_config(
        dataset=_Dataset.EARNINGS_EXPRESS,
        description="业绩快报(金额元)",
        typical_available_time=time(20, 30),
        depends_on=[_Dataset.STOCK_BASIC],
        critical_fields=["source_ticker", "ann_date", "report_date"],
        task_name="ingest_earnings_express",
        priority=60,
    ),
    _Dataset.INDEX_VALUATION: create_t1_config(
        dataset=_Dataset.INDEX_VALUATION,
        description="指数每日估值(市值元/股本股)",
        typical_available_time=time(19, 30),
        depends_on=[_Dataset.INDEX_BASIC],
        critical_fields=["instrument_id", "trade_date", "total_mv"],
        task_name="ingest_index_valuation",
        priority=46,
    ),
}


# ============ Query Functions ============


def get_datasets_by_tier(tier: TaskTier) -> list[_Dataset]:
    """Get all datasets belonging to a specific tier."""
    return [
        dataset for dataset, config in INGESTION_SPECS.items() if config.tier == tier
    ]


def get_dataset_config(dataset: _Dataset) -> DatasetSpec:
    """
    Get configuration for a specific dataset.

    Raises:
        DatasetNotFoundError: If dataset is not in registry.

    """
    if dataset not in INGESTION_SPECS:
        raise DatasetNotFoundError(dataset=str(dataset))
    return INGESTION_SPECS[dataset]


def get_dataset_config_by_value(dataset: DatasetRef | str) -> DatasetSpec:
    """Get configuration for a dataset reference by its value."""
    dataset_value = dataset if isinstance(dataset, str) else dataset.value

    for registered_dataset, config in INGESTION_SPECS.items():
        if registered_dataset.value == dataset_value:
            return config

    raise DatasetNotFoundError(dataset=dataset_value)


def iter_tier_datasets(tier: TaskTier) -> Iterator[tuple[_Dataset, DatasetSpec]]:
    """Iterate over all datasets in a tier with their configs."""
    for dataset in get_datasets_by_tier(tier):
        yield dataset, INGESTION_SPECS[dataset]


def get_all_datasets() -> list[_Dataset]:
    """Get all registered datasets."""
    return list(INGESTION_SPECS.keys())


def get_parallel_datasets(tier: TaskTier) -> list[list[_Dataset]]:
    """
    Get datasets grouped by dependency level for parallel execution.

    Datasets with no dependencies can run in parallel (level 0).
    Datasets with dependencies on level 0 run in parallel at level 1, etc.
    """
    datasets = get_datasets_by_tier(tier)
    if not datasets:
        return []

    tier_datasets = set(datasets)

    levels: list[list[_Dataset]] = []
    remaining = set(datasets)

    while remaining:
        level_datasets: list[_Dataset] = []
        for dataset in list(remaining):
            config = get_dataset_config(dataset)
            deps = [d for d in config.depends_on if d in tier_datasets]

            prev_level_datasets = {d for level in levels for d in level}
            if all(dep in prev_level_datasets for dep in deps):
                level_datasets.append(dataset)
                remaining.remove(dataset)

        if not level_datasets:
            levels.append(list(remaining))
            break

        levels.append(level_datasets)

    return levels
