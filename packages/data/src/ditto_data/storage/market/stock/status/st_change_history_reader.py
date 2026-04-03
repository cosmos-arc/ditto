"""StChangeHistoryReader - ST 状态变更历史读取接口."""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger


class StChangeHistoryReader:
    """
    ST 状态变更历史读取接口.

    提供：
    - get_st_status() - PIT 查询某证券在某日期的 ST 状态

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存读取.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 StChangeHistoryReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "StChangeHistoryReader initialized",
            event="st_change_history_reader_init_complete",
        )

    def get_st_status(
        self,
        instrument_id: int,
        as_of_date: str,
    ) -> dict[str, Any] | None:
        """
        PIT 查询证券在某日期的 ST 状态.

        使用标准 PIT 条件：
        effective_from <= as_of_date
        AND (effective_to IS NULL OR effective_to > as_of_date)

        Args:
            instrument_id: 证券 ID.
            as_of_date: 查询日期 (YYYY-MM-DD).

        Returns:
            包含 ST 状态的字典（is_st, st_type, effective_from），
            或 None 如果没有有效记录.

        """
        row = self._client.fetchone(
            """SELECT is_st, st_type, effective_from
            FROM st_change_history
            WHERE instrument_id = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY effective_from DESC
            LIMIT 1""",
            [instrument_id, as_of_date, as_of_date],
        )

        if row is None:
            return None

        return {
            "is_st": bool(row["is_st"]),
            "st_type": row["st_type"],
            "effective_from": row["effective_from"],
        }
