"""
Flow 辅助函数和上下文管理器。

该模块提供可复用的上下文管理器和辅助函数，
用于简化 flows 中的重复代码模式。
"""

from collections.abc import Iterator
from contextlib import contextmanager

from ditto_datahub import DataHub

from ditto_port.services.ingestion.coordinator import IngestionCoordinator


@contextmanager
def create_ingestion_context(
    data_root: str, source: str = "tushare"
) -> Iterator[tuple[DataHub, IngestionCoordinator]]:
    """
    创建摄取上下文，自动管理 DataHub 和 Coordinator 资源。

    该上下文管理器自动处理：
    1. 创建 DataHub 实例
    2. 获取指定的数据源
    3. 创建 IngestionCoordinator
    4. 确保 hub.close() 在退出时调用

    Args:
        data_root: DataHub 根目录
        source: 数据源名称，默认为 "tushare"

    Yields:
        tuple: (hub, coordinator) - DataHub 实例和 IngestionCoordinator 实例

    Example:
        with create_ingestion_context(
            data_root="data", source="tushare"
        ) as (hub, coordinator):
            # 使用 hub 和 coordinator
            result = coordinator.ingest(...)
        # hub 自动关闭

    """
    hub = DataHub(data_root=data_root)
    try:
        # 获取数据源
        data_source = hub.providers.get(source)

        # 创建协调器
        coordinator = IngestionCoordinator(
            hub=hub,
            source=data_source,
            source_name=source,
        )

        yield hub, coordinator
    finally:
        hub.close()
