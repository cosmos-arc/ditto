"""
Dataset specification models and factory functions.

Defines the core domain types for dataset configuration:
- DatasetRef Protocol, TaskTier enum, DatasetSpec and T1ConfigSpec models
- Factory functions create_t0_config() and create_t1_config()
"""

from __future__ import annotations

from datetime import time
from enum import StrEnum
from typing import Annotated, Protocol, overload

from ditto_data.models import Dataset as _Dataset
from pydantic import BaseModel, Field

__all__ = [
    "DEFAULT_INITIAL_CASH",
    "DatasetRef",
    "DatasetSpec",
    "T1ConfigSpec",
    "TaskTier",
    "create_t0_config",
    "create_t1_config",
]

DEFAULT_INITIAL_CASH: float = 1_000_000.0


class DatasetRef(Protocol):
    """Application-facing dataset reference."""

    @property
    def value(self) -> str:
        """Dataset identifier value."""
        ...


class TaskTier(StrEnum):
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
    dataset: _Dataset = Field(..., description="Dataset identifier")
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
    depends_on: list[_Dataset] = Field(
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

    dataset: _Dataset = Field(..., description="数据集标识符")
    description: str = Field(..., description="人类可读的描述")
    typical_available_time: time = Field(
        ...,
        description="数据典型可用时间",
    )
    depends_on: Annotated[
        list[_Dataset],
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


def create_t0_config(
    dataset: _Dataset,
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
    dataset: _Dataset,
    description: str,
    typical_available_time: time,
    depends_on: list[_Dataset],
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

    params = T1ConfigSpec.model_validate(
        {k: v for k, v in kwargs.items() if v is not None}
    )
    return create_t1_config(params)
