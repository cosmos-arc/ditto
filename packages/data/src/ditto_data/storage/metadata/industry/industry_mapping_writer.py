"""
Industry mapping writer for CQRS pattern.

Provides write access to stock-industry mapping with cache invalidation.
Following design document at docs/plans/2026-02-09-data-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_platform.foundation import DataCache, SQLiteClient, logger, traced

from ditto_data.models.metadata import IndustryMapping


class IndustryMappingWriter:
    """
    股票-行业映射写入器.

    提供股票-行业映射的写入访问，写操作后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 IndustryMappingWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.industry.update_mapping")
    def update_mapping(self, mapping: IndustryMapping) -> None:
        """
        更新股票的行业映射（同键最新观察胜出）.

        同键 = (instrument_id, industry_id, source, effective_from)。#593
        全量账本下同一成员会以 Y 行（开放区间）与退出后的 N 行
        （bounded 区间）跨轮次到达：键不得含 effective_to，否则
        Y→N 转换会留下永不闭合的幻影当前行（correctness F1/F2，
        2026-10-23 实证复现）。同键不同 effective_to = 退出边界修订
        或重开，按最新观察 UPDATE；同键同值幂等跳过。

        Args:
            mapping: 行业映射信息.

        Raises:
            Exception: 数据库操作失败时传播异常.

        """
        existing = self._client.fetchone(
            """SELECT id, effective_to FROM industry_mapping
            WHERE instrument_id = ? AND industry_id = ? AND source = ?
              AND effective_from IS ?""",
            [
                mapping.instrument_id,
                mapping.industry_id,
                mapping.source,
                mapping.effective_from,
            ],
        )
        if existing is not None:
            existing_to = existing["effective_to"]
            if existing_to == mapping.effective_to:
                return
            self._client.execute(
                """UPDATE industry_mapping
                SET effective_to = ?, entry_reason = ?
                WHERE id = ?""",
                [mapping.effective_to, mapping.entry_reason, existing["id"]],
            )
            self._client.commit()
            self._cache.invalidate_pattern("industry:mapping:*")
            logger.info(
                "Revised industry mapping interval",
                instrument_id=mapping.instrument_id,
                industry_id=mapping.industry_id,
                effective_from=mapping.effective_from,
                effective_to=mapping.effective_to,
            )
            return

        # 只有新的 current 映射才失效同来源旧 current；历史区间不得改写当前态。
        if mapping.effective_to is None:
            self._client.execute(
                """UPDATE industry_mapping
                SET effective_to = ?
                WHERE instrument_id = ? AND source = ? AND effective_to IS NULL""",
                [mapping.effective_from, mapping.instrument_id, mapping.source],
            )

        # 插入新映射
        self._client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from,
             effective_to, entry_reason)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [
                mapping.instrument_id,
                mapping.industry_id,
                mapping.source,
                mapping.effective_from,
                mapping.effective_to,
                mapping.entry_reason,
            ],
        )
        self._client.commit()

        # 失效相关缓存
        self._cache.invalidate_pattern("industry:mapping:*")

        logger.info(
            "Updated industry mapping",
            instrument_id=mapping.instrument_id,
            industry_id=mapping.industry_id,
            effective_from=mapping.effective_from,
        )
