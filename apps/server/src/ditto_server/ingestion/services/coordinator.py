"""
IngestionCoordinator - 统一摄取协调器。

职责：
- 提供统一的摄取入口点（单日/范围）
- 调用 Source 层获取数据
- 调用 MetadataManager 判断增量逻辑
- 调用 DataHub 写入数据
- 记录摄取日志到 IngestionLogStore

设计原则：
- 无状态设计（通过 DataHub 获取状态）
- 依赖注入（接受 DataHub 实例）
- 返回结构化结果（IngestionResult）

示例：
    hub = DataHub(data_root="data")
    source = hub.sources.tushare
    coordinator = IngestionCoordinator(hub, source)
    result = coordinator.ingest_date("etf_daily", "2024-12-31")
    hub.close()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ditto_datahub import DataHub


class IngestionCoordinator:
    """
    统一摄取协调器。

    负责：
    - 单日数据摄取（ingest_date）
    - 日期范围摄取（ingest_range）
    - 调用 Source 获取数据
    - 调用 MetadataManager 判断是否需要更新
    - 调用 DataHub 写入数据
    - 记录摄取日志
    """

    def __init__(self, hub: DataHub, source: str) -> None:
        """
        初始化协调器。

        Args:
            hub: DataHub 实例
            source: 数据源名称（如 "tushare"）

        """
        self.hub = hub
        self.source = source

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> dict[str, object]:
        """
        摄取单个交易日数据。

        Args:
            dataset: 数据集名称（如 "etf_daily"）
            trade_date: 交易日期（YYYY-MM-DD）
            force: 是否强制更新（忽略 checksum 缓存）

        Returns:
            摄取结果字典，包含：
            - success: bool
            - rows_fetched: int
            - rows_written: int
            - skipped: bool
            - error: str | None

        """
        # TODO: Task 1.3 实现
        raise NotImplementedError("Task 1.3: 待实现")

    def ingest_range(
        self,
        dataset: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> list[dict[str, object]]:
        """
        摄取日期范围数据。

        Args:
            dataset: 数据集名称
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            force: 是否强制更新

        Returns:
            摄取结果列表

        """
        # TODO: Task 1.3 实现
        raise NotImplementedError("Task 1.3: 待实现")
