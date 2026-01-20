"""
摄取协调器工厂.

提供创建 IngestionCoordinator 实例的工厂函数，
处理运行时参数（如 source_name）的依赖注入。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_datahub import DataHub
from ditto_datahub.models import Source

from ditto_port.services.ingestion.coordinator import IngestionCoordinator


@contextmanager
def create_coordinator(
    hub: DataHub, source_name: str | Source
) -> Iterator[IngestionCoordinator]:
    """
    创建 IngestionCoordinator 实例.

    Args:
        hub: DataHub 实例
        source_name: 数据源名称

    Yields:
        IngestionCoordinator: 协调器实例

    """
    # 支持 Source 枚举和字符串
    if isinstance(source_name, Source):
        source_key = source_name
    else:
        try:
            source_key = Source(source_name.lower())
        except ValueError as e:
            supported = [s.value for s in Source]
            raise ValueError(
                f"Unknown source: '{source_name}'. Supported sources: {supported}"
            ) from e

    # 获取数据源
    data_source = hub.sources.get(source_key)

    # 创建协调器
    coordinator = IngestionCoordinator(
        hub=hub,
        source=data_source,
        source_name=source_key.value,
    )

    yield coordinator
