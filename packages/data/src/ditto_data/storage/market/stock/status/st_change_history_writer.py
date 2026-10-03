"""StChangeHistoryWriter - ST 状态变更历史写入接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import DataCache, SQLiteClient, logger, traced


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

    def __init__(self, client: SQLiteClient, cache: DataCache[Any] | None) -> None:
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

    def save_history_rows(
        self,
        rows: list[dict[str, object]],
    ) -> int:
        """
        批量写入带证据的 ST 变更历史行（摄取路径，幂等）。

        每行必须携带真实生效日期（effective_from）与可知时间（observed_at）；
        版本键包括 instrument_id、effective_from、source、observed_at。
        同内容保留首次可知时间；变化内容追加版本。缺生效日期时拒绝写入。

        Args:
            rows: 行字典，键含 instrument_id/effective_from/is_st/st_type/
                effective_to/source/observed_at.

        Returns:
            写入行数.

        """
        written = 0
        for row in rows:
            effective_from = row.get("effective_from")
            if effective_from is None or str(effective_from).strip() == "":
                raise ValueError("st change history row lacks a real effective date")
            previous = self._client.fetchone(
                """SELECT * FROM st_change_history
                   WHERE instrument_id = ? AND effective_from = ? AND source = ?
                   ORDER BY datetime(observed_at) DESC LIMIT 1""",
                [
                    row["instrument_id"],
                    str(effective_from),
                    str(row.get("source") or "tushare"),
                ],
            )
            if previous is not None and all(
                previous[field] == row.get(field)
                for field in ("is_st", "st_type", "effective_to")
            ):
                written += 1
                continue
            visible_at = row.get("observed_at")
            if previous is not None:
                visible_at = row.get("recorded_at", visible_at)
            if not visible_at:
                raise ValueError("history version requires knowledge time")
            self._client.execute(
                """INSERT INTO st_change_history
                (instrument_id, effective_from, is_st, st_type, effective_to,
                 source, observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    row["instrument_id"],
                    str(effective_from),
                    1 if row.get("is_st") else 0,
                    row.get("st_type"),
                    row.get("effective_to"),
                    str(row.get("source") or "tushare"),
                    visible_at,
                ],
            )
            written += 1
        if written:
            self._client.commit()
            if self._cache is not None:
                self._cache.invalidate_pattern("st_change_history:*")
        return written

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
        if self._cache is not None:
            self._cache.invalidate_pattern("st_change_history:*")

        logger.info(
            "ST change recorded",
            event="st_change_record_complete",
            instrument_id=instrument_id,
            is_st=curr_is_st,
            st_type=st_type,
            effective_from=trade_date,
        )
