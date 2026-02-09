"""
Identity reader for CQRS pattern.

Provides read-only access to identity mapping data with PIT support.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_foundation import logger, traced


class IdentityReader:
    """
    Identity 映射读取器.

    提供 identity 映射的只读访问，支持 PIT 查询。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于查询结果缓存.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 IdentityReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.identity.resolve_instrument_id")
    def resolve_instrument_id(
        self,
        source_ticker: str,
        source: str,
        asof: str | None = None,
    ) -> int | None:
        """
        解析 source_ticker 到 instrument_id（支持 PIT）.

        Args:
            source_ticker: 数据源原始代码.
            source: 数据源标识.
            asof: 时间点日期，None 表示当前.

        Returns:
            instrument_id 或 None（如果未找到）.

        """
        logger.debug(
            "Starting identity Instrument ID resolution",
            event="identity_instrument_id_resolve_start",
            source_ticker=source_ticker,
            source=source,
            asof=asof,
        )

        # 尝试从缓存获取
        cache_key = f"identity:instrument_id:{source}:{source_ticker}:asof={asof}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建 SQL 查询
        if asof:
            # PIT mode: 查询历史映射
            row = self._client.fetchone(
                """SELECT instrument_id FROM identity_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, source_ticker, asof, asof],
            )
        else:
            # Current mode: 只查询当前有效映射（更快）
            row = self._client.fetchone(
                """SELECT instrument_id FROM identity_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_to IS NULL""",
                [source, source_ticker],
            )

        instrument_id = int(row["instrument_id"]) if row else None

        # 缓存结果
        if instrument_id is not None:
            self._cache.set(cache_key, instrument_id)

        if instrument_id:
            logger.debug(
                "Identity Instrument ID resolved successfully",
                event="identity_instrument_id_resolve_complete",
                source_ticker=source_ticker,
                instrument_id=instrument_id,
            )
        else:
            logger.warning(
                "Identity Instrument ID not found",
                event="identity_instrument_id_resolve_not_found",
                source_ticker=source_ticker,
                source=source,
                asof=asof,
            )

        return instrument_id

    @traced("data.identity.resolve_instrument_ids_batch")
    def resolve_instrument_ids_batch(
        self,
        source_tickers: list[str],
        source: str,
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析 source_tickers 到 instrument_ids.

        Args:
            source_tickers: 数据源原始代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            字典，映射 source_ticker 到 instrument_id（仅包含找到的代码）.

        """
        logger.info(
            "Starting batch identity Instrument ID resolution",
            event="identity_instrument_id_batch_resolve_start",
            source=source,
            asof=asof,
            input_count=len(source_tickers),
        )

        result: dict[str, int] = {}
        for code in source_tickers:
            instrument_id = self.resolve_instrument_id(code, source, asof)
            if instrument_id:
                result[code] = instrument_id

        logger.info(
            "Batch identity Instrument ID resolution completed",
            event="identity_instrument_id_batch_resolve_complete",
            requested=len(source_tickers),
            found=len(result),
            not_found=len(source_tickers) - len(result),
        )

        return result

    @traced("data.identity.get_source_ticker")
    def get_source_ticker(
        self,
        instrument_id: int,
        source: str,
        asof: str | None = None,
    ) -> str | None:
        """
        反向查询：instrument_id 到 source_ticker.

        Args:
            instrument_id: 证券内部标识符.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            source_ticker 或 None（如果未找到）.

        """
        # 尝试从缓存获取
        cache_key = f"identity:source_ticker:{instrument_id}:{source}:asof={asof}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建 SQL 查询
        if asof:
            row = self._client.fetchone(
                """SELECT source_ticker FROM identity_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [instrument_id, source, asof, asof],
            )
        else:
            row = self._client.fetchone(
                """SELECT source_ticker FROM identity_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_to IS NULL""",
                [instrument_id, source],
            )

        result = str(row["source_ticker"]) if row else None

        # 缓存结果
        if result is not None:
            self._cache.set(cache_key, result)

        return result
