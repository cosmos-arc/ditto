"""RebalanceWriter - 标的池调仓日程写入接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import logger, traced
from ditto_platform.foundation.cache import DataCache

from ditto_data.storage.sqlite_client import SQLiteClient


class RebalanceWriter:
    """
    标的池调仓日程写入接口.

    提供：
    - record_rebalance() - 记录调仓日程

    所有写操作完成后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 RebalanceWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "RebalanceWriter initialized",
            event="rebalance_writer_init_complete",
        )

    @traced("data.universe.record_rebalance")
    def record_rebalance(
        self,
        universe_id: str,
        rebalance_date: str,
        description: str | None = None,
    ) -> None:
        """
        记录标的池调仓日程.

        Args:
            universe_id: 标的池 ID.
            rebalance_date: 调仓日期 (YYYY-MM-DD).
            description: 可选描述.

        """
        logger.info(
            "Recording rebalance schedule",
            event="rebalance_record_start",
            universe_id=universe_id,
            rebalance_date=rebalance_date,
        )

        self._client.execute(
            """INSERT INTO universe_rebalance
            (universe_id, rebalance_date, description)
            VALUES (?, ?, ?)""",
            [universe_id, rebalance_date, description],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:rebalance:*")

        logger.info(
            "Rebalance schedule recorded",
            event="rebalance_record_complete",
            universe_id=universe_id,
            rebalance_date=rebalance_date,
        )
