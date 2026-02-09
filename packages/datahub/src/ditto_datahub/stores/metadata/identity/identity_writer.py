"""
Identity writer for CQRS pattern.

Provides write access to identity mapping with cache invalidation.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_foundation import logger, traced


class IdentityWriter:
    """
    Identity 映射写入器.

    提供 identity 映射的写入访问，写操作后自动失效相关缓存。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于缓存失效.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 IdentityWriter.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.identity.register")
    def register(
        self,
        instrument_id: int,
        source_ticker: str,
        source: str,
        effective_from: str,
        is_primary: bool = True,
    ) -> None:
        """
        注册 identity_mapping 记录.

        Args:
            instrument_id: 证券内部标识符.
            source_ticker: 数据源原始代码.
            source: 数据源标识.
            effective_from: 生效开始日期.
            is_primary: 是否主标识符.

        Raises:
            Exception: 数据库操作失败时传播异常.

        """
        logger.info(
            "Starting identity registration",
            event="identity_register_start",
            instrument_id=instrument_id,
            source_ticker=source_ticker,
            source=source,
            effective_from=effective_from,
            is_primary=is_primary,
        )

        try:
            self._client.execute(
                """INSERT INTO identity_mapping
                (instrument_id, source, source_ticker, effective_from, is_primary)
                VALUES (?, ?, ?, ?, ?)""",
                [
                    instrument_id,
                    source,
                    source_ticker,
                    effective_from,
                    1 if is_primary else 0,
                ],
            )

            self._client.commit()

            # 失效相关缓存
            self._cache.invalidate_pattern("identity:*")

            logger.info(
                "Identity registered successfully",
                event="identity_register_complete",
                instrument_id=instrument_id,
                source_ticker=source_ticker,
                source=source,
            )

        except Exception as e:
            logger.error(
                "Identity registration failed",
                event="identity_register_failed",
                instrument_id=instrument_id,
                source_ticker=source_ticker,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
