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

from datetime import time
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Iterator


class Dataset(str, Enum):
    """
    Dataset enumeration for type-safe dataset references.

    Values match the dataset names used in DataHub and ingestion tasks.
    """

    # T0: Meta datasets
    CALENDAR = "calendar"
    STOCK_BASIC = "stock_basic"
    ETF_BASIC = "etf_basic"

    # T1: Incremental datasets
    ETF_DAILY = "etf_daily"
    STOCK_DAILY = "stock_daily"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"


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


class DatasetConfig(BaseModel):
    """
    Configuration for a single dataset.

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
        default_factory=list,
        description="Datasets that must complete before this one",
    )
    retry_limit: int = Field(default=3, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=300, description="Task timeout in seconds")
    quality_checks_enabled: bool = Field(
        default=True,
        description="Whether to run quality checks",
    )
    critical_fields: list[str] = Field(
        default_factory=list,
        description="Critical fields for quality validation",
    )

    # Extended fields
    task_name: str = Field(..., description="Prefect task name")
    requires_trade_date: bool = Field(
        default=False,
        description="Whether task requires trade_date parameter",
    )


# ============ Helper Functions ============


def create_t0_config(  # noqa: PLR0913
    dataset: Dataset,
    description: str,
    typical_available_time: time,
    critical_fields: list[str],
    task_name: str,
    timeout_seconds: int = 300,
) -> DatasetConfig:
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
        DatasetConfig instance

    """
    return DatasetConfig(
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


def create_t1_config(  # noqa: PLR0913
    dataset: Dataset,
    description: str,
    typical_available_time: time,
    depends_on: list[Dataset],
    critical_fields: list[str],
    task_name: str,
    priority: int = 20,
    timeout_seconds: int = 300,
) -> DatasetConfig:
    """
    Create a T1 incremental dataset configuration.

    T1 datasets are daily incremental data with these defaults:
    - tier: T1_INCREMENTAL
    - retry_limit: 3
    - quality_checks_enabled: True
    - requires_trade_date: True
    - update_frequency: "每日"

    Args:
        dataset: Dataset identifier
        description: Human-readable description
        typical_available_time: Typical time when data is available
        depends_on: Datasets that must complete before this one
        critical_fields: Critical fields for quality validation
        task_name: Prefect task name to execute
        priority: Execution priority (default: 20)
        timeout_seconds: Task timeout in seconds (default: 300)

    Returns:
        DatasetConfig instance

    """
    return DatasetConfig(
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


# ============ Dataset Registry ============

DATASET_REGISTRY: dict[Dataset, DatasetConfig] = {
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
        dataset for dataset, config in DATASET_REGISTRY.items() if config.tier == tier
    ]


def get_dataset_config(dataset: Dataset) -> DatasetConfig:
    """
    Get configuration for a specific dataset.

    Args:
        dataset: Dataset enum value

    Returns:
        DatasetConfig instance

    Raises:
        KeyError: If dataset is not in registry

    Examples:
        >>> config = get_dataset_config(Dataset.ETF_DAILY)
        >>> assert config.tier == TaskTier.T1_INCREMENTAL

    """
    if dataset not in DATASET_REGISTRY:
        raise KeyError(f"Dataset {dataset} not found in registry")
    return DATASET_REGISTRY[dataset]


def iter_tier_datasets(tier: TaskTier) -> Iterator[tuple[Dataset, DatasetConfig]]:
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
        yield dataset, DATASET_REGISTRY[dataset]


def get_all_datasets() -> list[Dataset]:
    """
    Get all registered datasets.

    Returns:
        List of all Dataset enum values in the registry

    Examples:
        >>> all_datasets = get_all_datasets()
        >>> assert Dataset.CALENDAR in all_datasets

    """
    return list(DATASET_REGISTRY.keys())


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
        >>> # T1 datasets all depend on T0 datasets, so they are all level 0
        >>> levels = get_parallel_datasets(TaskTier.T1_INCREMENTAL)
        >>> assert len(levels[0]) == 4  # etf_daily, stock_daily, adj_factor, fund_adj

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
