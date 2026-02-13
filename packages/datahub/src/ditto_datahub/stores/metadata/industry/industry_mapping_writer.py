"""
Industry mapping writer for CQRS pattern.

Provides write access to stock-industry mapping with cache invalidation.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced

from ditto_datahub.models.metadata import IndustryMapping


class IndustryMappingWriter:
    """
    股票-行业映射写入器.

    提供股票-行业映射的写入访问，写操作后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: Any, cache: Any) -> None:
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
        更新股票的行业映射.

        先失效旧映射记录，然后插入新映射。

        Args:
            mapping: 行业映射信息.

        Raises:
            Exception: 数据库操作失败时传播异常.

        """
        # 失效旧映射：将当前 effective_to 设为 None 的记录设置为失效
        self._client.execute(
            """UPDATE industry_mapping
            SET effective_to = ?
            WHERE instrument_id = ? AND effective_to IS NULL""",
            [mapping.effective_from, mapping.instrument_id],
        )

        # 插入新映射
        self._client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from,
             effective_to, entry_reason)
            VALUES (?, ?, 'sw', ?, NULL, ?)""",
            [
                mapping.instrument_id,
                mapping.industry_id,
                mapping.effective_from,
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
