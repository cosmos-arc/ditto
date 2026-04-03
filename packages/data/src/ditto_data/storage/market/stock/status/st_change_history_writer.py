"""StChangeHistoryWriter - ST 状态变更历史写入接口."""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced


class StChangeHistoryWriter:
    """
    ST 状态变更历史写入接口.

    提供：
    - record_st_change() - 检测并记录 ST 状态变更

    当 is_st 或 st_type 发生变化时，关闭前一条记录并插入新记录。
    所有写操作完成后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 StChangeHistoryWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "StChangeHistoryWriter initialized",
            event="st_change_history_writer_init_complete",
        )

    @traced("data.market.record_st_change")
    def record_st_change(
        self,
        instrument_id: int,
        prev_is_st: bool,
        curr_is_st: bool,
        st_type: str | None,
        trade_date: str,
    ) -> None:
        """
        检测并记录 ST 状态变更.

        当 is_st 或 st_type 发生变化时：
        1. 关闭该证券当前有效记录（设置 effective_to = trade_date）
        2. 插入新的变更记录

        Args:
            instrument_id: 证券 ID.
            prev_is_st: 前一交易日的 is_st 状态.
            curr_is_st: 当前交易日的 is_st 状态.
            st_type: 当前 ST 类型（ST/ST*/SST 等），非 ST 时为 None.
            trade_date: 当前交易日期 (YYYY-MM-DD).

        """
        # is_st 未变化且 st_type 未变化时跳过
        if prev_is_st == curr_is_st and (
            prev_is_st is False  # 非 ST 状态下不关注 st_type
        ):
            logger.debug(
                "No ST status change detected",
                event="st_change_skip",
                instrument_id=instrument_id,
                trade_date=trade_date,
            )
            return

        # 查找该证券当前有效记录（effective_to IS NULL）
        current = self._client.fetchone(
            """SELECT id, st_type FROM st_change_history
            WHERE instrument_id = ? AND effective_to IS NULL""",
            [instrument_id],
        )

        # 关闭当前有效记录
        if current is not None:
            prev_st_type = current["st_type"]
            # is_st 和 st_type 都没变化则跳过
            if prev_is_st == curr_is_st and prev_st_type == st_type:
                logger.debug(
                    "No ST status change detected (same st_type)",
                    event="st_change_skip",
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                )
                return
            self._client.execute(
                """UPDATE st_change_history
                SET effective_to = ?
                WHERE id = ?""",
                [trade_date, current["id"]],
            )

        # 插入新的变更记录
        is_st_int = 1 if curr_is_st else 0
        self._client.execute(
            """INSERT INTO st_change_history
            (instrument_id, effective_from, is_st, st_type)
            VALUES (?, ?, ?, ?)""",
            [instrument_id, trade_date, is_st_int, st_type],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("st_change_history:*")

        logger.info(
            "ST change recorded",
            event="st_change_record_complete",
            instrument_id=instrument_id,
            is_st=curr_is_st,
            st_type=st_type,
            effective_from=trade_date,
        )
