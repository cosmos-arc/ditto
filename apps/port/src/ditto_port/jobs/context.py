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
from ditto_datahub.services import IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService

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
) -> Iterator[tuple[Any, Any]]:
    """
    创建摄取上下文，使用 dishka 容器管理依赖.

    该上下文管理器自动处理：
    1. 创建 dishka 容器
    2. 获取所需的 Services
    3. 使用工厂创建 IngestionCoordinator
    4. 确保容器在退出时关闭

    Args:
        source: 数据源名称，默认为 "tushare"

    Yields:
        tuple: (metadata_service, coordinator) - MetadataService 实例和  # noqa: E501
            IngestionCoordinator 实例

    Example:
        with create_ingestion_context(source="tushare") as (  # noqa: E501
            metadata_service, coordinator
        ):
            result = coordinator.ingest(...)

    """
    with create_prefect_host() as container:
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        fundamental_service = container.get(FundamentalService)
        capital_service = container.get(CapitalService)
        macro_service = container.get(MacroService)
        source_service = container.get(SourceService)
        ingestion_log_service = container.get(IngestionLogService)
        with create_coordinator(
            metadata_service=metadata_service,
            market_service=market_service,
            fundamental_service=fundamental_service,
            capital_service=capital_service,
            macro_service=macro_service,
            source_service=source_service,
            ingestion_log_service=ingestion_log_service,
            source_name=source,
        ) as coordinator:
            yield metadata_service, coordinator


@contextmanager
def create_metadata_context() -> Iterator[MetadataService]:
    """
    创建 MetadataService 上下文，使用 dishka 容器管理依赖.

    用于只需要 MetadataService 的场景（如检查交易日等）。

    Yields:
        MetadataService: 容器管理的 MetadataService 实例

    Example:
        with create_metadata_context() as metadata_service:
            result = metadata_service.is_trading_day(date)

    """
    with create_prefect_host() as container:
        yield container.get(MetadataService)


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
def create_dq_and_metadata_context() -> Iterator[
    tuple[QualityEngine, MetadataService, MarketService]
]:
    """
    创建 DQ、MetadataService 和 MarketService 上下文，使用 dishka 容器管理依赖.

    用于同时需要 QualityEngine、MetadataService 和 MarketService 的场景。

    Yields:
        tuple: (QualityEngine, MetadataService, MarketService) - 容器管理的实例

    Example:
        with create_dq_and_metadata_context() as (  # noqa: E501
            engine, metadata_service, market_service
        ):
            result = engine.check(...)

    """
    with create_prefect_host() as container:
        yield (
            container.get(QualityEngine),
            container.get(MetadataService),
            container.get(MarketService),
        )


@contextmanager
def create_ingestion_log_context() -> Iterator[
    tuple[MetadataService, IngestionLogService]
]:
    """
    创建 MetadataService 和 IngestionLogService 上下文.

    用于需要 MetadataService 和 IngestionLogService 的场景（如回补管理器）。

    Yields:
        tuple: (MetadataService, IngestionLogService) - 容器管理的实例

    """
    with create_prefect_host() as container:
        yield (
            container.get(MetadataService),
            container.get(IngestionLogService),
        )
