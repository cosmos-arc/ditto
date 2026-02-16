"""
Dataset configuration registry for data ingestion.

This module defines the central registry of all datasets with their configuration,
including task tier, dependencies, and task mappings.

The registry enables:
1. Dynamic task generation based on tier
2. Dependency-aware execution orchestration
3. Type-safe dataset references
4. Consistent configuration across ingestion system
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import time
from enum import Enum
from typing import Annotated, cast, overload

from ditto_datahub.models import Dataset
from pydantic import BaseModel, Field


class TaskTier(str, Enum):
    """
    Task tier enumeration for scheduling and orchestration.

    Tiers define the execution priority and dependencies:
    - T0: Meta data (calendar, basic info) - foundation
    - T1: Daily incremental data - parallel execution
    - T2: Repair and backfill - fix missing data
    - T3: Quality checks - validate data integrity
    """

    T0_META = "t0_meta"  # Meta data: calendar, basic info
    T1_INCREMENTAL = "t1_incremental"  # Daily incremental data
    T2_REPAIR = "t2_repair"  # Repair and backfill
    T3_QUALITY = "t3_quality"  # Quality checks


class DatasetSpec(BaseModel):
    """
    Configuration for a single dataset.

    配置文件解析模型：使用 lax 模式允许类型转换。
    数据集配置由代码定义，无需从配置文件加载。

    Attributes:
        dataset: Dataset identifier (Dataset enum)
        tier: Task tier for scheduling (T0/T1/T2/T3)
        description: Human-readable description
        update_frequency: Update frequency string (e.g., "每日", "实时")
        typical_available_time: Typical time when data is available
        priority: Execution priority (lower = higher priority)
        depends_on: List of datasets that must complete first
        retry_limit: Maximum retry attempts on failure
        timeout_seconds: Task timeout in seconds
        quality_checks_enabled: Whether to run quality checks
        critical_fields: Critical fields for quality validation
        task_name: Prefect task name to execute
        requires_trade_date: Whether task needs trade_date parameter

    """

    # Spec-required fields
    dataset: Dataset = Field(..., description="Dataset identifier")
    tier: TaskTier = Field(..., description="Task tier for scheduling")
    description: str = Field(..., description="Human-readable description")
    update_frequency: str = Field(
        ...,
        description="Update frequency (e.g., '每日', '实时')",
    )
    typical_available_time: time = Field(
        ...,
        description="Typical time when data is available",
    )
    priority: int = Field(
        ...,
        description="Execution priority (lower = higher priority)",
    )
    depends_on: list[Dataset] = Field(
        default_factory=lambda: [],
        description="Datasets that must complete before this one",
    )
    retry_limit: int = Field(default=3, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=300, description="Task timeout in seconds")
    quality_checks_enabled: bool = Field(
        default=True,
        description="Whether to run quality checks",
    )
    critical_fields: list[str] = Field(
        default_factory=lambda: [],
        description="Critical fields for quality validation",
    )

    # Extended fields
    task_name: str = Field(..., description="Prefect task name")
    requires_trade_date: bool = Field(
        default=False,
        description="Whether task requires trade_date parameter",
    )


# ============ Configuration Parameters ============


class T1ConfigSpec(BaseModel):
    """
    T1 数据集配置参数。

    配置文件解析模型：使用 lax 模式允许类型转换。
    封装 T1 数据集配置所需的所有参数，简化 create_t1_config 函数调用。

    Attributes:
        dataset: 数据集标识符
        description: 人类可读的描述
        typical_available_time: 数据典型可用时间
        depends_on: 依赖的数据集列表
        critical_fields: 质量验证的关键字段
        task_name: Prefect 任务名称
        priority: 执行优先级（默认 20）
        timeout_seconds: 任务超时时间（默认 300）

    """

    dataset: Dataset = Field(..., description="数据集标识符")
    description: str = Field(..., description="人类可读的描述")
    typical_available_time: time = Field(
        ...,
        description="数据典型可用时间",
    )
    depends_on: Annotated[
        list[Dataset],
        Field(default_factory=list, description="依赖的数据集列表"),
    ]
    critical_fields: Annotated[
        list[str],
        Field(default_factory=list, description="质量验证的关键字段"),
    ]
    task_name: str = Field(..., description="Prefect 任务名称")
    priority: int = Field(
        default=20,
        description="执行优先级(数字越小优先级越高)",
    )
    timeout_seconds: int = Field(default=300, description="任务超时时间(秒)")


# ============ Helper Functions ============


def _validate_dataset_list(value: object) -> list[Dataset]:
    """
    验证并收窄类型为 list[Dataset].

    Args:
        value: 待验证的值

    Returns:
        验证后的 list[Dataset]

    Raises:
        TypeError: 如果值不是 list 或包含非 Dataset 元素

    """
    if not isinstance(value, list):
        msg = "depends_on must be a list"
        raise TypeError(msg)
    # 使用 cast 告诉类型检查器这是 list[object]
    for item in cast(list[object], value):
        if not isinstance(item, Dataset):
            msg = "depends_on must contain only Dataset enum values"
            raise TypeError(msg)
    # 经过验证后，可以安全地 cast 为 list[Dataset]
    return cast(list[Dataset], value)


def _validate_string_list(value: object) -> list[str]:
    """
    验证并收窄类型为 list[str].

    Args:
        value: 待验证的值

    Returns:
        验证后的 list[str]

    Raises:
        TypeError: 如果值不是 list 或包含非字符串元素

    """
    if not isinstance(value, list):
        msg = "value must be a list"
        raise TypeError(msg)
    # 使用 cast 告诉类型检查器这是 list[object]
    for item in cast(list[object], value):
        if not isinstance(item, str):
            msg = "list must contain only strings"
            raise TypeError(msg)
    # 经过验证后，可以安全地 cast 为 list[str]
    return cast(list[str], value)


def create_t0_config(
    dataset: Dataset,
    description: str,
    typical_available_time: time,
    critical_fields: list[str],
    task_name: str,
    timeout_seconds: int = 300,
) -> DatasetSpec:
    """
    Create a T0 meta dataset configuration.

    T0 datasets are foundational metadata with these defaults:
    - tier: T0_META
    - priority: 10
    - depends_on: []
    - retry_limit: 3
    - quality_checks_enabled: True
    - requires_trade_date: False
    - update_frequency: "每日"

    Args:
        dataset: Dataset identifier
        description: Human-readable description
        typical_available_time: Typical time when data is available
        critical_fields: Critical fields for quality validation
        task_name: Prefect task name to execute
        timeout_seconds: Task timeout in seconds (default: 300)

    Returns:
        DatasetSpec instance

    """
    return DatasetSpec(
        dataset=dataset,
        tier=TaskTier.T0_META,
        description=description,
        update_frequency="每日",
        typical_available_time=typical_available_time,
        priority=10,
        depends_on=[],
        retry_limit=3,
        timeout_seconds=timeout_seconds,
        quality_checks_enabled=True,
        critical_fields=critical_fields,
        task_name=task_name,
        requires_trade_date=False,
    )


@overload
def create_t1_config(params: T1ConfigSpec) -> DatasetSpec: ...


@overload
def create_t1_config(
    *,
    dataset: Dataset,
    description: str,
    typical_available_time: time,
    depends_on: list[Dataset],
    critical_fields: list[str],
    task_name: str,
    priority: int = 20,
    timeout_seconds: int = 300,
) -> DatasetSpec: ...


def create_t1_config(
    params: T1ConfigSpec | None = None,
    **kwargs: object,
) -> DatasetSpec:
    """
    Create a T1 incremental dataset configuration.

    T1 datasets are daily incremental data with these defaults:
    - tier: T1_INCREMENTAL
    - retry_limit: 3
    - quality_checks_enabled: True
    - requires_trade_date: True
    - update_frequency: "每日"

    支持两种调用方式：

    1. 使用 T1ConfigSpec 对象（推荐）:
        >>> params = T1ConfigSpec(
        ...     dataset=Dataset.ETF_DAILY,
        ...     description="ETF日行情数据",
        ...     typical_available_time=time(18, 0),
        ...     depends_on=[Dataset.ETF_BASIC],
        ...     critical_fields=["trade_date", "ts_code"],
        ...     task_name="ingest_etf_bars",
        ... )
        >>> config = create_t1_config(params)

    2. 使用关键字参数（向后兼容）:
        >>> config = create_t1_config(
        ...     dataset=Dataset.ETF_DAILY,
        ...     description="ETF日行情数据",
        ...     typical_available_time=time(18, 0),
        ...     depends_on=[Dataset.ETF_BASIC],
        ...     critical_fields=["trade_date", "ts_code"],
        ...     task_name="ingest_etf_bars",
        ... )

    Returns:
        DatasetSpec 实例

    """
    # 检查是否使用 T1ConfigSpec 对象
    if params is not None:
        return DatasetSpec(
            dataset=params.dataset,
            tier=TaskTier.T1_INCREMENTAL,
            description=params.description,
            update_frequency="每日",
            typical_available_time=params.typical_available_time,
            priority=params.priority,
            depends_on=params.depends_on,
            retry_limit=3,
            timeout_seconds=params.timeout_seconds,
            quality_checks_enabled=True,
            critical_fields=params.critical_fields,
            task_name=params.task_name,
            requires_trade_date=True,
        )

    # 使用关键字参数方式
    dataset = kwargs.get("dataset")
    description = kwargs.get("description")
    typical_available_time = kwargs.get("typical_available_time")
    depends_on = kwargs.get("depends_on")
    critical_fields = kwargs.get("critical_fields")
    task_name = kwargs.get("task_name")
    priority = kwargs.get("priority", 20)
    timeout_seconds = kwargs.get("timeout_seconds", 300)

    # 验证必需参数
    if not isinstance(dataset, Dataset):
        msg = "dataset is required and must be a Dataset enum"
        raise TypeError(msg)
    if not isinstance(description, str):
        msg = "description is required and must be a string"
        raise TypeError(msg)
    if not isinstance(typical_available_time, time):
        msg = "typical_available_time is required and must be a time object"
        raise TypeError(msg)
    # 使用辅助函数验证并收窄类型
    depends_on = _validate_dataset_list(depends_on)
    critical_fields = _validate_string_list(critical_fields)
    if not isinstance(task_name, str):
        msg = "task_name is required and must be a string"
        raise TypeError(msg)
    if not isinstance(priority, int):
        msg = "priority must be an integer"
        raise TypeError(msg)
    if not isinstance(timeout_seconds, int):
        msg = "timeout_seconds must be an integer"
        raise TypeError(msg)

    # 类型收窄（经过验证后安全）
    return DatasetSpec(
        dataset=dataset,
        tier=TaskTier.T1_INCREMENTAL,
        description=description,
        update_frequency="每日",
        typical_available_time=typical_available_time,
        priority=priority,
        depends_on=depends_on,
        retry_limit=3,
        timeout_seconds=timeout_seconds,
        quality_checks_enabled=True,
        critical_fields=critical_fields,
        task_name=task_name,
        requires_trade_date=True,
    )


# ============ Ingestion Specs ============

INGESTION_SPECS: dict[Dataset, DatasetSpec] = {
    # T0: Meta datasets
    Dataset.CALENDAR: create_t0_config(
        dataset=Dataset.CALENDAR,
        description="交易日历",
        typical_available_time=time(8, 0),
        critical_fields=["cal_date", "is_trade"],
        task_name="ingest_calendar",
        timeout_seconds=60,
    ),
    Dataset.STOCK_BASIC: create_t0_config(
        dataset=Dataset.STOCK_BASIC,
        description="股票基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "symbol", "name", "market", "list_date"],
        task_name="ingest_stock_basic",
    ),
    Dataset.ETF_BASIC: create_t0_config(
        dataset=Dataset.ETF_BASIC,
        description="ETF基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "symbol", "name", "list_date"],
        task_name="ingest_etf_basic",
    ),
    Dataset.INDEX_BASIC: create_t0_config(
        dataset=Dataset.INDEX_BASIC,
        description="指数基础信息",
        typical_available_time=time(8, 30),
        critical_fields=["ts_code", "name", "market"],
        task_name="ingest_index_basic",
    ),
    # T1: Incremental datasets
    Dataset.ETF_DAILY: create_t1_config(
        dataset=Dataset.ETF_DAILY,
        description="ETF日行情数据",
        typical_available_time=time(18, 0),
        depends_on=[Dataset.ETF_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "vol",
        ],
        task_name="ingest_etf_bars",
    ),
    Dataset.INDEX_DAILY: create_t1_config(
        dataset=Dataset.INDEX_DAILY,
        description="指数日行情数据",
        typical_available_time=time(18, 0),
        depends_on=[Dataset.INDEX_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "vol",
        ],
        task_name="ingest_index_daily",
        priority=15,
    ),
    Dataset.STOCK_DAILY: create_t1_config(
        dataset=Dataset.STOCK_DAILY,
        description="股票日行情数据",
        typical_available_time=time(17, 0),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=[
            "trade_date",
            "ts_code",
            "open",
            "high",
            "low",
            "close",
            "vol",
        ],
        task_name="ingest_stock_daily",
        timeout_seconds=600,
    ),
    Dataset.STOCK_STATUS: create_t1_config(
        dataset=Dataset.STOCK_STATUS,
        description="股票状态数据",
        typical_available_time=time(17, 30),
        depends_on=[Dataset.STOCK_DAILY],
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
    Dataset.ADJ_FACTOR: create_t1_config(
        dataset=Dataset.ADJ_FACTOR,
        description="复权因子",
        typical_available_time=time(19, 0),
        depends_on=[Dataset.STOCK_DAILY],
        critical_fields=["trade_date", "ts_code", "adj_factor"],
        task_name="ingest_adj_factor",
        priority=30,
    ),
    Dataset.FUND_ADJ: create_t1_config(
        dataset=Dataset.FUND_ADJ,
        description="ETF/基金复权因子",
        typical_available_time=time(19, 0),
        depends_on=[Dataset.ETF_DAILY],
        critical_fields=["trade_date", "ts_code", "adj_factor"],
        task_name="ingest_fund_adj",
        priority=30,
    ),
    Dataset.BALANCE_SHEET: create_t1_config(
        dataset=Dataset.BALANCE_SHEET,
        description="资产负债表",
        typical_available_time=time(20, 30),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_balance_sheet",
        priority=35,
        timeout_seconds=900,
    ),
    Dataset.INCOME_STATEMENT: create_t1_config(
        dataset=Dataset.INCOME_STATEMENT,
        description="利润表",
        typical_available_time=time(20, 30),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_income_statement",
        priority=35,
        timeout_seconds=900,
    ),
    Dataset.CASH_FLOW: create_t1_config(
        dataset=Dataset.CASH_FLOW,
        description="现金流量表",
        typical_available_time=time(20, 30),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_cash_flow",
        priority=35,
        timeout_seconds=900,
    ),
    Dataset.DIVIDEND: create_t1_config(
        dataset=Dataset.DIVIDEND,
        description="分红送配数据",
        typical_available_time=time(20, 0),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "ex_dividend_date", "knowledge_date"],
        task_name="ingest_dividend",
        priority=40,
    ),
    Dataset.VALUATION_METRICS: create_t1_config(
        dataset=Dataset.VALUATION_METRICS,
        description="估值指标",
        typical_available_time=time(19, 30),
        depends_on=[Dataset.STOCK_DAILY],
        critical_fields=["instrument_id", "trade_date", "knowledge_date"],
        task_name="ingest_valuation_metrics",
        priority=45,
    ),
    Dataset.MARGIN_TRADING: create_t1_config(
        dataset=Dataset.MARGIN_TRADING,
        description="融资融券",
        typical_available_time=time(19, 30),
        depends_on=[Dataset.STOCK_DAILY],
        critical_fields=["instrument_id", "trade_date", "knowledge_date"],
        task_name="ingest_margin_trading",
        priority=45,
    ),
    Dataset.PLEDGE_RATIO: create_t1_config(
        dataset=Dataset.PLEDGE_RATIO,
        description="股权质押",
        typical_available_time=time(21, 0),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "report_date", "knowledge_date"],
        task_name="ingest_pledge_ratio",
        priority=50,
    ),
    Dataset.MACRO_INDICATORS: create_t1_config(
        dataset=Dataset.MACRO_INDICATORS,
        description="宏观指标",
        typical_available_time=time(21, 30),
        depends_on=[Dataset.CALENDAR],
        critical_fields=["indicator_code", "date", "value"],
        task_name="ingest_macro_indicators",
        priority=55,
    ),
    Dataset.FUTURES_POSITION: create_t1_config(
        dataset=Dataset.FUTURES_POSITION,
        description="期货持仓数据",
        typical_available_time=time(21, 0),
        depends_on=[Dataset.CALENDAR],
        critical_fields=["instrument_id", "trade_date", "knowledge_date"],
        task_name="ingest_futures_position",
        priority=60,
    ),
    Dataset.CORPORATE_ACTIONS: create_t1_config(
        dataset=Dataset.CORPORATE_ACTIONS,
        description="公司行为",
        typical_available_time=time(20, 0),
        depends_on=[Dataset.STOCK_BASIC],
        critical_fields=["instrument_id", "action_type", "effective_date"],
        task_name="ingest_corporate_actions",
        priority=65,
    ),
}


# ============ Helper Functions ============


def get_datasets_by_tier(tier: TaskTier) -> list[Dataset]:
    """
    Get all datasets belonging to a specific tier.

    Args:
        tier: Task tier to filter by (T0/T1/T2/T3)

    Returns:
        List of datasets in the specified tier

    Examples:
        >>> t0_datasets = get_datasets_by_tier(TaskTier.T0_META)
        >>> assert Dataset.CALENDAR in t0_datasets

    """
    return [
        dataset for dataset, config in INGESTION_SPECS.items() if config.tier == tier
    ]


def get_dataset_config(dataset: Dataset) -> DatasetSpec:
    """
    Get configuration for a specific dataset.

    Args:
        dataset: Dataset enum value

    Returns:
        DatasetSpec instance

    Raises:
        KeyError: If dataset is not in registry

    Examples:
        >>> config = get_dataset_config(Dataset.ETF_DAILY)
        >>> assert config.tier == TaskTier.T1_INCREMENTAL

    """
    if dataset not in INGESTION_SPECS:
        raise KeyError(f"Dataset {dataset} not found in registry")
    return INGESTION_SPECS[dataset]


def iter_tier_datasets(tier: TaskTier) -> Iterator[tuple[Dataset, DatasetSpec]]:
    """
    Iterate over all datasets in a tier with their configs.

    Args:
        tier: Task tier to iterate over

    Yields:
        Tuples of (dataset, config)

    Examples:
        >>> for dataset, config in iter_tier_datasets(TaskTier.T1_INCREMENTAL):
        ...     print(f"{dataset.name}: {config.description}")

    """
    for dataset in get_datasets_by_tier(tier):
        yield dataset, INGESTION_SPECS[dataset]


def get_all_datasets() -> list[Dataset]:
    """
    Get all registered datasets.

    Returns:
        List of all Dataset enum values in the registry

    Examples:
        >>> all_datasets = get_all_datasets()
        >>> assert Dataset.CALENDAR in all_datasets

    """
    return list(INGESTION_SPECS.keys())


def get_parallel_datasets(tier: TaskTier) -> list[list[Dataset]]:
    """
    Get datasets grouped by dependency level for parallel execution.

    Datasets with no dependencies can run in parallel (level 0).
    Datasets with dependencies on level 0 run in parallel at level 1, etc.

    Args:
        tier: Task tier to analyze

    Returns:
        List of levels, where each level is a list of datasets that can run in parallel

    Examples:
        >>> # T1 datasets按依赖分层并行执行
        >>> levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)
        >>> assert len(levels) >= 1

    """
    datasets = get_datasets_by_tier(tier)
    if not datasets:
        return []

    # Filter to only dependencies within the same tier
    # Dependencies on other tiers (e.g., T1 depending on T0)
    # don't affect parallel execution
    tier_datasets = set(datasets)

    levels: list[list[Dataset]] = []
    remaining = set(datasets)

    while remaining:
        # Find datasets whose intra-tier dependencies are in previous levels
        level_datasets: list[Dataset] = []
        for dataset in list(remaining):
            config = get_dataset_config(dataset)
            # Only consider dependencies within the same tier
            deps = [d for d in config.depends_on if d in tier_datasets]

            # Check if all intra-tier dependencies are in previous levels
            prev_level_datasets = {d for level in levels for d in level}
            if all(dep in prev_level_datasets for dep in deps):
                level_datasets.append(dataset)
                remaining.remove(dataset)

        if not level_datasets:
            # No progress - circular dependency or all remaining have external deps
            # Put remaining in current level
            levels.append(list(remaining))
            break

        levels.append(level_datasets)

    return levels
