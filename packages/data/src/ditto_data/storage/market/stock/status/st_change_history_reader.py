"""StChangeHistoryReader - ST 状态变更历史读取接口."""

from __future__ import annotations

from typing import Any

from ditto_data.storage.metadata.instrument.instrument_reader import build_in_clause
from ditto_platform.foundation import DataCache, SQLiteClient, logger


class StChangeHistoryReader:
    """
    ST 状态变更历史读取接口.

    提供：
    - get_st_status() - PIT 查询某证券在某日期的 ST 状态

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存读取.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any] | None) -> None:
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
        *,
        cutoff: str | None = None,
    ) -> dict[str, Any] | None:
        """
        PIT 查询证券在某日期的 ST 状态.

        使用标准 PIT 条件：
        effective_from <= as_of_date
        AND (effective_to IS NULL OR effective_to > as_of_date)

        提供 cutoff（知识截止时刻）时只使用该时刻之前已记录的行：
        晚到的 ST 事件不能进入更早的 cutoff（秒粒度 fail closed）。

        Args:
            instrument_id: 证券 ID.
            as_of_date: 查询日期 (YYYY-MM-DD).
            cutoff: 知识截止时刻 (YYYY-MM-DD HH:MM:SS)，可选.

        Returns:
            包含 ST 状态的字典（is_st, st_type, effective_from），
            或 None 如果没有有效记录.

        """
        sql = """SELECT is_st, st_type, effective_from
            FROM st_change_history
            WHERE instrument_id = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)"""
        params: list[Any] = [instrument_id, as_of_date, as_of_date]
        if cutoff is not None:
            sql += " AND (observed_at IS NULL OR datetime(observed_at) < datetime(?))"
            params.append(cutoff)
        sql += " ORDER BY effective_from DESC LIMIT 1"
        row = self._client.fetchone(sql, params)

        if row is None:
            return None

        return {
            "is_st": bool(row["is_st"]),
            "st_type": row["st_type"],
            "effective_from": row["effective_from"],
        }

    def get_st_status_batch(
        self,
        instrument_ids: list[int],
        as_of_date: str,
        *,
        cutoff: str | None = None,
    ) -> dict[int, dict[str, Any]]:
        """
        批量 PIT 查询多证券在某日期的 ST 状态.

        只返回有覆盖记录的证券；无证据（含历史起点之前）不返回键，
        调用方据此区分"证据缺失"与"证据为非 ST"。

        Args:
            instrument_ids: 证券 ID 列表.
            as_of_date: 查询日期 (YYYY-MM-DD).
            cutoff: 知识截止时刻，提供时隐藏该时刻之后记录的行.

        Returns:
            {instrument_id: {"is_st", "st_type", "effective_from"}} 映射.

        """
        if not instrument_ids:
            return {}
        in_clause, in_params = build_in_clause("instrument_id", instrument_ids)
        knowledge_filter = ""
        cutoff_params: list[Any] = []
        if cutoff is not None:
            knowledge_filter = (
                " AND (observed_at IS NULL OR datetime(observed_at) < datetime(?))"
            )
            cutoff_params.append(cutoff)
        rows = self._client.fetchall(
            f"""SELECT instrument_id, is_st, st_type, effective_from FROM (
                    SELECT instrument_id, is_st, st_type, effective_from,
                           ROW_NUMBER() OVER (
                               PARTITION BY instrument_id
                               ORDER BY effective_from DESC
                           ) AS rn
                    FROM st_change_history
                    WHERE effective_from <= ?
                      AND (effective_to IS NULL OR effective_to > ?)
                      {knowledge_filter}
                      AND {in_clause}
                )
            WHERE rn = 1""",  # noqa: S608 - in_clause 通过 _build_in_clause 安全构建
            [as_of_date, as_of_date, *cutoff_params, *in_params],
        )
        return {
            int(row["instrument_id"]): {
                "is_st": bool(row["is_st"]),
                "st_type": row["st_type"],
                "effective_from": row["effective_from"],
            }
            for row in rows
        }
