"""
RetryManager - 重试管理器。

职责：
- 重试失败的任务
- 支持按最大重试次数筛选
- 支持按日期范围筛选
- 限制重试数量以防资源耗尽

设计原则：
- 从 IngestionLogStore 查询失败记录
- 调用 IngestionCoordinator.ingest_date() 执行重试
- 记录重试结果

示例：
    hub = DataHub(data_root="data")
    source = hub.sources.tushare
    coordinator = IngestionCoordinator(hub, source)
    retry_mgr = RetryManager(hub, coordinator)
    result = retry_mgr.retry_failed(
        dataset="etf_daily",
        max_attempts=3,
        limit=10,
    )
    hub.close()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_datahub import DataHub

    from ditto_server.ingestion.services.coordinator import IngestionCoordinator


class RetryManager:
    """
    重试管理器。

    负责：
    - 查询失败任务
    - 执行重试
    - 记录重试结果
    """

    def __init__(self, hub: DataHub, coordinator: IngestionCoordinator) -> None:
        """
        初始化重试管理器。

        Args:
            hub: DataHub 实例
            coordinator: IngestionCoordinator 实例

        """
        self.hub = hub
        self.coordinator = coordinator

    def retry_failed(
        self,
        dataset: str,
        max_attempts: int = 3,
        limit: int = 10,
    ) -> dict[str, object]:
        """
        重试失败的任务。

        Args:
            dataset: 数据集名称
            max_attempts: 最大重试次数（筛选条件）
            limit: 最多重试多少条记录

        Returns:
            重试结果字典，包含：
            - total_retried: int
            - success_count: int
            - still_failed_count: int
            - errors: list[str]

        """
        # TODO: Task 2.2 实现
        raise NotImplementedError("Task 2.2: 待实现")

    def get_failed_dates(
        self,
        dataset: str,
        max_attempts: int | None = None,
        limit: int = 100,
    ) -> list[str]:
        """
        获取失败日期列表。

        Args:
            dataset: 数据集名称
            max_attempts: 最大尝试次数（None 表示不限制）
            limit: 返回数量上限

        Returns:
            失败日期列表（YYYY-MM-DD）

        """
        # TODO: Task 2.2 实现
        raise NotImplementedError("Task 2.2: 待实现")
