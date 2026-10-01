"""NameHistoryReader - 证券名称变更历史读取接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import DataCache, SQLiteClient, logger

from ditto_data.storage.metadata.instrument.instrument_reader import build_in_clause


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

    def get_names_batch(self, instrument_ids: list[int], asof: str) -> dict[int, str]:
        """
        批量获取多个证券在指定时间点的名称（PIT）.

        单次 SQL 查询解析每个证券 changed_date <= asof 的最新记录，
        未命中（无历史或不在请求列表）不返回键.

        Args:
            instrument_ids: 证券 ID 列表.
            asof: Point-in-Time 日期 (YYYY-MM-DD).

        Returns:
            {instrument_id: name} 映射（仅包含有历史记录的证券）.

        """
        if not instrument_ids:
            return {}
        in_clause, params = build_in_clause("instrument_id", instrument_ids)
        rows = self._client.fetchall(
            f"""SELECT instrument_id, new_name FROM (
                    SELECT instrument_id, new_name,
                           ROW_NUMBER() OVER (
                               PARTITION BY instrument_id
                               ORDER BY changed_date DESC
                           ) AS rn
                    FROM instrument_name_history
                    WHERE changed_date <= ? AND instrument_id IN ({in_clause})
                )
            WHERE rn = 1""",  # noqa: S608 - in_clause 通过 _build_in_clause 安全构建
            [asof, *params],
        )
        return {int(row["instrument_id"]): str(row["new_name"]) for row in rows}

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
