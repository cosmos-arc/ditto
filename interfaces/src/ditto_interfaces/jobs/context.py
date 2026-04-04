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

from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade
from ditto_app.types import QualityEngine

from ditto_interfaces.registry.container import make_app_container


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
def create_dq_and_metadata_context() -> Iterator[
    tuple[QualityEngine, MetadataQueryFacade, MarketQueryFacade]
]:
    """
    创建 DQ、MetadataQueryFacade 和 MarketQueryFacade 上下文，使用 dishka 容器管理依赖.

    用于同时需要 QualityEngine、MetadataQueryFacade 和 MarketQueryFacade 的场景。

    Yields:
        tuple: (QualityEngine, MetadataQueryFacade, MarketQueryFacade) - 容器管理的实例

    Example:
        with create_dq_and_metadata_context() as (  # noqa: E501
            engine, metadata_facade, market_facade
        ):
            result = engine.check(...)

    """
    with create_prefect_host() as container:
        yield (
            container.get(QualityEngine),
            container.get(MetadataQueryFacade),
            container.get(MarketQueryFacade),
        )
