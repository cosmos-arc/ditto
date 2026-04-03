"""
Industry writer for CQRS pattern.

Provides write access to industry master data with cache invalidation.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced

from ditto_data.models.metadata import IndustryBasic


class IndustryWriter:
    """
    申万行业主数据写入器.

    提供行业主数据的写入访问，写操作后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 IndustryWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.industry.register")
    def register(self, industry: IndustryBasic) -> None:
        """
        注册或更新行业信息.

        Args:
            industry: 行业基本信息.

        Raises:
            Exception: 数据库操作失败时传播异常.

        """
        logger.info(
            "Starting industry registration",
            event="industry_register_start",
            industry_id=industry.industry_id,
            industry_name=industry.industry_name,
        )

        try:
            self._client.execute(
                """INSERT OR REPLACE INTO industry_basic
                (industry_id, industry_name, industry_level,
                 parent_id, is_active, source)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    industry.industry_id,
                    industry.industry_name,
                    industry.industry_level,
                    industry.parent_id,
                    1 if industry.is_active else 0,
                    industry.source,
                ],
            )
            self._client.commit()

            # 失效相关缓存
            self._cache.invalidate_pattern("industry:*")

            logger.info(
                "Industry registered successfully",
                event="industry_register_complete",
                industry_id=industry.industry_id,
            )

        except Exception as e:
            logger.error(
                "Industry registration failed",
                event="industry_register_failed",
                industry_id=industry.industry_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
