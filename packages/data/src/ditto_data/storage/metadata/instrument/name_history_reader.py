"""NameHistoryReader - 证券名称变更历史读取接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import logger
from ditto_platform.foundation.cache import DataCache
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient


class NameHistoryReader:
    """
    证券名称变更历史读取接口.

    提供：
    - get_name() - 获取指定时间点的证券名称（PIT）
    - list_name_changes() - 列出所有名称变更（按时间倒序）

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于查询结果缓存.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 NameHistoryReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "NameHistoryReader initialized",
            event="name_history_reader_init_complete",
        )

    def get_name(self, instrument_id: int, asof: str) -> str | None:
        """
        获取证券在指定时间点的名称.

        查询 changed_date <= asof 的最新记录，返回 new_name.

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 日期 (YYYY-MM-DD).

        Returns:
            证券名称或 None（未找到时）.

        """
        row = self._client.fetchone(
            """SELECT new_name FROM instrument_name_history
            WHERE instrument_id = ? AND changed_date <= ?
            ORDER BY changed_date DESC LIMIT 1""",
            [instrument_id, asof],
        )
        return row["new_name"] if row else None

    def list_name_changes(self, instrument_id: int) -> list[dict[str, Any]]:
        """
        列出证券的所有名称变更.

        Args:
            instrument_id: 证券 ID.

        Returns:
            名称变更列表（按 changed_date 倒序）.

        """
        rows = self._client.fetchall(
            """SELECT * FROM instrument_name_history
            WHERE instrument_id = ?
            ORDER BY changed_date DESC""",
            [instrument_id],
        )
        return [dict(r) for r in rows]
