"""UniverseWriter - 证券域写入接口."""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced
from ditto_infra.foundation.cache import DataCache

from ditto_data.storage.sqlite_client import SQLiteClient


class UniverseWriter:
    """
    证券域写入接口。

    提供：
    - create_universe() - 创建新的证券域
    - add_constituents() - 批量添加成分股
    - remove_constituent() - 移除成分股（设置 effective_to）

    所有写操作完成后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问
        _cache: 缓存管理器，用于缓存失效

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 UniverseWriter。

        Args:
            client: SQLite 客户端实例
            cache: 缓存管理器实例

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "UniverseWriter initialized",
            event="universe_writer_init_complete",
        )

    @traced("data.universe_create")
    def create_universe(
        self,
        universe_id: str,
        name: str,
        description: str | None = None,
        universe_type: str = "custom",
        source_ref: str | None = None,
    ) -> None:
        """
        创建新的证券域。

        Args:
            universe_id: 证券域唯一标识符
            name: 证券域显示名称
            description: 可选描述
            universe_type: 证券域类型（custom、index、sector 等）
            source_ref: 可选的外部引用（如指数代码）

        Raises:
            sqlite3.IntegrityError: 如果 universe_id 已存在

        """
        logger.info(
            "Creating universe",
            event="universe_create_start",
            universe_id=universe_id,
            name=name,
            universe_type=universe_type,
            source_ref=source_ref,
        )

        self._client.execute(
            """INSERT INTO universe
            (universe_id, name, description, universe_type, source_ref)
            VALUES (?, ?, ?, ?, ?)""",
            [universe_id, name, description, universe_type, source_ref],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:*")

        logger.info(
            "Universe created successfully",
            event="universe_create_complete",
            universe_id=universe_id,
        )

    @traced("data.universe_delete")
    def delete_universe(self, universe_id: str) -> None:
        """
        删除证券域及其所有成分股.

        Args:
            universe_id: 证券域唯一标识符

        """
        logger.info(
            "Deleting universe",
            event="universe_delete_start",
            universe_id=universe_id,
        )

        self._client.execute(
            "DELETE FROM universe_constituent WHERE universe_id = ?",
            [universe_id],
        )
        self._client.execute(
            "DELETE FROM universe WHERE universe_id = ?",
            [universe_id],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:*")
        self._cache.invalidate_pattern("universe:constituents:*")

        logger.info(
            "Universe deleted successfully",
            event="universe_delete_complete",
            universe_id=universe_id,
        )

    @traced("data.universe_add_constituents")
    def add_constituents(
        self,
        universe_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """
        批量添加成分股到证券域。

        Args:
            universe_id: 证券域标识符
            records: 成分股记录列表，每条记录应包含：
                - instrument_id: 证券 ID（必需）
                - effective_from: 生效起始日期（必需）
                - effective_to: 生效结束日期（可选）
                - weight: 权重（可选，默认 1.0）
                - source: 数据源（可选）
                - source_ticker: 源代码（可选）

        Returns:
            添加的记录数量

        """
        if not records:
            return 0

        logger.info(
            "Adding constituents to universe",
            event="universe_add_constituents_start",
            universe_id=universe_id,
            record_count=len(records),
        )

        # 准备批量插入参数
        params_list: list[list[Any] | tuple[Any, ...]] = []
        for record in records:
            params = (
                universe_id,
                record.get("instrument_id"),
                record.get("effective_from"),
                record.get("effective_to"),
                record.get("weight", 1.0),
                record.get("source"),
                record.get("source_ticker"),
            )
            params_list.append(params)

        self._client.executemany(
            """INSERT INTO universe_constituent
            (
                universe_id, instrument_id, effective_from, effective_to,
                weight, source, source_ticker
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            params_list,
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:constituents:*")

        logger.info(
            "Constituents added successfully",
            event="universe_add_constituents_complete",
            universe_id=universe_id,
            count=len(records),
        )

        return len(records)

    @traced("data.universe_remove_constituent")
    def remove_constituent(
        self,
        universe_id: str,
        instrument_id: int,
        effective_date: str,
    ) -> None:
        """
        通过设置 effective_to 日期移除成分股。

        Args:
            universe_id: 证券域标识符
            instrument_id: 要移除的证券 ID
            effective_date: 成分股失效日期

        """
        logger.info(
            "Removing constituent from universe",
            event="universe_remove_constituent_start",
            universe_id=universe_id,
            instrument_id=instrument_id,
            effective_date=effective_date,
        )

        # 更新活跃记录的 effective_to
        self._client.execute(
            """UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND instrument_id = ? AND effective_to IS NULL""",
            [effective_date, universe_id, instrument_id],
        )
        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:constituents:*")

        logger.info(
            "Constituent removed successfully",
            event="universe_remove_constituent_complete",
            universe_id=universe_id,
            instrument_id=instrument_id,
        )

    @traced("data.universe_replace_constituents")
    def replace_constituents(
        self,
        universe_id: str,
        records: list[dict[str, Any]],
        effective_date: str,
    ) -> int:
        """
        原子替换标的池所有当前成分股.

        在事务中：
        1. 关闭所有当前成分（SET effective_to = effective_date）
        2. 批量插入新成分

        Args:
            universe_id: 标的池 ID.
            records: 新成分列表，每条需包含 instrument_id 和 effective_from.
            effective_date: 当前成分的失效日期.

        Returns:
            新增的成分数量.

        """
        if not records:
            return 0

        logger.info(
            "Replacing universe constituents",
            event="universe_replace_constituents_start",
            universe_id=universe_id,
            record_count=len(records),
            effective_date=effective_date,
        )

        # 关闭当前成分
        self._client.execute(
            """UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND effective_to IS NULL""",
            [effective_date, universe_id],
        )

        # 批量插入新成分
        params_list: list[list[Any] | tuple[Any, ...]] = []
        for record in records:
            params = (
                universe_id,
                record.get("instrument_id"),
                record.get("effective_from"),
                record.get("effective_to"),
                record.get("weight", 1.0),
                record.get("source"),
                record.get("source_ticker"),
            )
            params_list.append(params)

        self._client.executemany(
            """INSERT INTO universe_constituent
            (
                universe_id, instrument_id, effective_from, effective_to,
                weight, source, source_ticker
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            params_list,
        )

        self._client.commit()

        # 失效缓存
        self._cache.invalidate_pattern("universe:constituents:*")

        logger.info(
            "Constituents replaced successfully",
            event="universe_replace_constituents_complete",
            universe_id=universe_id,
            count=len(records),
        )

        return len(records)
