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
            "effective_from",
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
