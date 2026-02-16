"""
Prefect 任务上下文管理（使用 dishka 同步容器）.

该模块提供 Prefect 任务/Flow 使用的上下文管理器，
替代之前的 create_ingestion_context，使用 dishka 管理依赖生命周期。

注意：create_ingestion_context 和 create_ingestion_log_context 已被
registry/contexts/ingestion.py 中的 create_ingestion_bundle 替代。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ditto_core.quality import QualityEngine
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService

from ditto_port.registry.container import make_app_container


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
    container = make_app_container()
    try:
        yield container
    finally:
        container.close()


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
