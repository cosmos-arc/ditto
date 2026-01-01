"""
MetadataManager - 元数据管理器。

职责：
- 计算数据 checksum（用于判断数据是否变化）
- 比较新旧数据
- 判断是否需要跳过摄取（基于 checksum 和游标）
- 管理 IngestionLogStore 和 IngestionCursorStore

设计原则：
- 无状态设计
- 通过 IngestionLogStore 获取历史 checksum
- 通过 IngestionCursorStore 获取游标信息

示例：
    hub = DataHub(data_root="data")
    manager = MetadataManager(hub)
    should_skip, reason = manager.should_skip("etf_daily", "2024-12-31")
    hub.close()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from ditto_datahub import DataHub


class MetadataManager:
    """
    元数据管理器。

    负责：
    - 计算 checksum
    - 比较新旧数据
    - 判断是否跳过摄取
    """

    def __init__(self, hub: DataHub) -> None:
        """
        初始化元数据管理器。

        Args:
            hub: DataHub 实例

        """
        self.hub = hub
        self.log_store = hub.ingestion_log
        self.cursor_store = hub.ingestion_cursor

    def compute_checksum(self, df: pl.DataFrame) -> str:
        """
        计算数据的 checksum。

        Args:
            df: polars DataFrame

        Returns:
            checksum 字符串（基于行数、schema、数据内容）

        """
        # TODO: Task 1.2 实现
        raise NotImplementedError("Task 1.2: 待实现")

    def should_skip(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """
        判断是否应该跳过摄取。

        Args:
            dataset: 数据集名称
            trade_date: 交易日期
            force: 是否强制更新（忽略跳过判断）

        Returns:
            (should_skip, reason) 元组
            - should_skip: 是否跳过
            - reason: 跳过原因（如果不跳过则为 None）

        """
        # TODO: Task 1.2 实现
        raise NotImplementedError("Task 1.2: 待实现")

    def compare_data(
        self,
        new_df: pl.DataFrame,
        existing_log: dict[str, object],
    ) -> bool:
        """
        比较新旧数据是否相同。

        Args:
            new_df: 新获取的数据
            existing_log: 现有的摄取日志（包含 checksum）

        Returns:
            数据是否相同（True 表示相同，无需更新）

        """
        # TODO: Task 1.2 实现
        raise NotImplementedError("Task 1.2: 待实现")
