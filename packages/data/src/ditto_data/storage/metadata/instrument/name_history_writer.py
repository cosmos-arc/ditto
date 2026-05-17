"""NameHistoryWriter - 证券名称变更历史写入接口."""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import DataCache, SQLiteClient, logger, traced


class NameHistoryWriter:
    """
    证券名称变更历史写入接口.

    提供：
    - record_name_change() - 记录名称变更

    所有写操作完成后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 NameHistoryWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "NameHistoryWriter initialized",
            event="name_history_writer_init_complete",
        )

    @traced("data.instrument.record_name_change")
    def record_name_change(
        self,
        instrument_id: int,
        old_name: str,
        new_name: str,
        changed_date: str,
    ) -> None:
        """
        记录证券名称变更.

        Args:
            instrument_id: 证券 ID.
            old_name: 变更前的名称.
            new_name: 变更后的名称.
            changed_date: 变更日期 (YYYY-MM-DD).

        """
        logger.info(
            "Recording name change",
            event="name_change_record_start",
            instrument_id=instrument_id,
            old_name=old_name,
            new_name=new_name,
            changed_date=changed_date,
        )

        self._client.execute(
            """INSERT INTO instrument_name_history
            (instrument_id, old_name, new_name, changed_date)
            VALUES (?, ?, ?, ?)""",
            [instrument_id, old_name, new_name, changed_date],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("instrument:name_history:*")

        logger.info(
            "Name change recorded",
            event="name_change_record_complete",
            instrument_id=instrument_id,
        )
