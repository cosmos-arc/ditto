"""
IngestionCursorService - 数据摄入游标服务.

封装 Reader/Writer，为 Port 层提供统一的摄入游标管理接口.
"""

from __future__ import annotations

from datetime import datetime

from ditto_infra.foundation import logger

from ditto_datahub.models.ingestion import IngestionCursor
from ditto_datahub.stores.runtime.ingestion.ingestion_cursor_reader import (
    IngestionCursorReader,
)
from ditto_datahub.stores.runtime.ingestion.ingestion_cursor_writer import (
    IngestionCursorWriter,
)


class IngestionCursorService:
    """
    数据摄入游标服务.

    封装 IngestionCursorReader 和 IngestionCursorWriter，提供统一的摄入游标管理接口。

    职责：
    - 追踪每个数据集的最后成功/尝试摄入日期
    - 提供快速查询接口
    """

    def __init__(
        self,
        cursor_reader: IngestionCursorReader,
        cursor_writer: IngestionCursorWriter,
    ) -> None:
        """
        初始化 IngestionCursorService.

        Args:
            cursor_reader: 摄入游标读取器实例
            cursor_writer: 摄入游标写入器实例

        """
        self._reader = cursor_reader
        self._writer = cursor_writer

    def update_cursor(
        self,
        dataset: str,
        source: str,
        last_success: str | None = None,
        last_attempted: str | None = None,
    ) -> IngestionCursor:
        """
        更新摄入游标.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（如 "tushare"）
            last_success: 最后成功的交易日期（YYYY-MM-DD）
            last_attempted: 最后尝试的交易日期（YYYY-MM-DD）

        Returns:
            更新后的摄入游标对象

        """
        cursor = IngestionCursor(
            dataset=dataset,
            source=source,
            last_success=last_success,
            last_attempted=last_attempted,
            updated_at=datetime.now().isoformat(),
        )
        result = self._writer.upsert_cursor(cursor)

        logger.debug(
            "Ingestion cursor updated",
            event="ingestion_cursor_updated",
            dataset=dataset,
            source=source,
            last_success=last_success,
            last_attempted=last_attempted,
        )

        return result

    def get_cursor(
        self,
        dataset: str,
        source: str,
    ) -> IngestionCursor | None:
        """
        获取指定数据集的摄入游标.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（如 "tushare"）

        Returns:
            摄入游标对象，不存在时返回 None

        """
        return self._reader.get_cursor(dataset, source)

    def list_cursors(self, source: str | None = None) -> list[IngestionCursor]:
        """
        列出所有摄入游标，可按 source 过滤.

        Args:
            source: 可选的数据源标识过滤

        Returns:
            摄入游标列表

        """
        return self._reader.list_cursors(source)

    def get_last_success(
        self,
        dataset: str,
        source: str = "tushare",
    ) -> str | None:
        """
        获取数据集最后成功的摄入日期.

        Args:
            dataset: 数据集名称（如 "stock_daily"）
            source: 数据源标识（默认 "tushare"）

        Returns:
            最后成功的交易日期（YYYY-MM-DD），不存在时返回 None

        """
        return self._reader.get_last_success(dataset, source)
