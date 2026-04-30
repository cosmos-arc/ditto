"""RebalanceReader - 标的池调仓日程读取接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import logger
from ditto_platform.foundation.cache import DataCache

from ditto_data.storage.sqlite_client import SQLiteClient


class RebalanceReader:
    """
    标的池调仓日程读取接口.

    提供：
    - get_next_rebalance() - 获取下一次调仓日程
    - list_rebalances() - 列出所有调仓日程

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于查询结果缓存.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 RebalanceReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "RebalanceReader initialized",
            event="rebalance_reader_init_complete",
        )

    def get_next_rebalance(
        self,
        universe_id: str,
        after_date: str,
    ) -> dict[str, Any] | None:
        """
        获取标的池下一次调仓日程.

        Args:
            universe_id: 标的池 ID.
            after_date: 查询此日期之后的调仓日程.

        Returns:
            调仓日程字典或 None（未找到时）.

        """
        row = self._client.fetchone(
            """SELECT * FROM universe_rebalance
            WHERE universe_id = ? AND rebalance_date > ?
            ORDER BY rebalance_date ASC LIMIT 1""",
            [universe_id, after_date],
        )
        return dict(row) if row else None

    def list_rebalances(self, universe_id: str) -> list[dict[str, Any]]:
        """
        列出标的池所有调仓日程.

        Args:
            universe_id: 标的池 ID.

        Returns:
            调仓日程列表（按 rebalance_date 倒序）.

        """
        rows = self._client.fetchall(
            """SELECT * FROM universe_rebalance
            WHERE universe_id = ?
            ORDER BY rebalance_date DESC""",
            [universe_id],
        )
        return [dict(r) for r in rows]
