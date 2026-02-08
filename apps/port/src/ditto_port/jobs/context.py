"""
Prefect 任务上下文管理（使用 dishka 同步容器）.

该模块提供 Prefect 任务/Flow 使用的上下文管理器，
替代之前的 create_ingestion_context，使用 dishka 管理依赖生命周期。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from dishka import make_container
from ditto_core.quality import QualityEngine
from ditto_datahub import DataHub

from ditto_port.registry import (
    ConfigProvider,
    CoreProvider,
    DataHubProvider,
    DataSourcesProvider,
    DomainServiceProvider,
)
from ditto_port.services.ingestion import create_coordinator


@contextmanager
def create_prefect_host() -> Iterator[Any]:
    """
    Prefect Host - 任务级容器生命周期管理.

    用于单个 Prefect 任务或 Flow 的生命周期：
    - 创建容器
    - 初始化所有组件
    - 优雅关闭

    Yields:
        dishka 同步容器实例

    """
    container = make_container(
        ConfigProvider(),
        CoreProvider(),
        DomainServiceProvider(),
        DataHubProvider(),
        DataSourcesProvider(),
    )
    try:
        yield container
    finally:
        container.close()


@contextmanager
def create_ingestion_context(
    source: str = "tushare",
) -> Iterator[tuple[DataHub, Any]]:
    """
    创建摄取上下文，使用 dishka 容器管理依赖.

    该上下文管理器自动处理：
    1. 创建 dishka 容器
    2. 获取 DataHub 实例
    3. 使用工厂创建 IngestionCoordinator
    4. 确保容器在退出时关闭

    Args:
        source: 数据源名称，默认为 "tushare"

    Yields:
        tuple: (hub, coordinator) - DataHub 实例和 IngestionCoordinator 实例

    Example:
        with create_ingestion_context(source="tushare") as (hub, coordinator):
            result = coordinator.ingest(...)

    """
    with create_prefect_host() as container:
        hub = container.get(DataHub)
        with create_coordinator(hub=hub, source_name=source) as coordinator:
            yield hub, coordinator


@contextmanager
def create_datahub_context() -> Iterator[DataHub]:
    """
    创建 DataHub 上下文，使用 dishka 容器管理依赖.

    用于只需要 DataHub 的场景（如 DQ 检查、监控等）。

    Yields:
        DataHub: 容器管理的 DataHub 实例

    Example:
        with create_datahub_context() as hub:
            result = hub.calendar.is_trading_day(date)

    """
    with create_prefect_host() as container:
        yield container.get(DataHub)


@contextmanager
def create_dq_context() -> Iterator[QualityEngine]:
    """
    创建 DQ 上下文，使用 dishka 容器管理依赖.

    用于需要 QualityEngine 的场景（如 DQ 批量检查）。

    Yields:
        QualityEngine: 容器管理的 QualityEngine 实例

    Example:
        with create_dq_context() as engine:
            result = engine.check(...)

    """
    with create_prefect_host() as container:
        yield container.get(QualityEngine)


@contextmanager
def create_dq_and_datahub_context() -> Iterator[tuple[QualityEngine, DataHub]]:
    """
    创建 DQ 和 DataHub 上下文，使用 dishka 容器管理依赖.

    用于同时需要 QualityEngine 和 DataHub 的场景。

    Yields:
        tuple: (QualityEngine, DataHub) - 容器管理的实例

    Example:
        with create_dq_and_datahub_context() as (engine, hub):
            result = engine.check(...)

    """
    with create_prefect_host() as container:
        yield container.get(QualityEngine), container.get(DataHub)
