"""
Industry mapping reader for CQRS pattern.

Provides read-only access to stock-industry mapping data with PIT support.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import traced


class IndustryMappingReader:
    """
    股票-行业映射读取器.

    提供股票-行业映射的只读访问，支持 PIT 查询。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于查询结果缓存.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 IndustryMappingReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.industry.get_stocks")
    def get_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取行业的所有成分股.

        Args:
            industry_id: 行业 ID.
            asof: Point-in-time 查询日期，None 表示查询当前.

        Returns:
            Instrument ID 列表.

        """
        # 尝试从缓存获取
        cache_key = f"industry:mapping:stocks:{industry_id}:asof={asof}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建 SQL 查询
        if asof:
            sql = """
                SELECT instrument_id FROM industry_mapping
                WHERE industry_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY instrument_id
            """
            params = [industry_id, asof, asof]
        else:
            sql = """
                SELECT instrument_id FROM industry_mapping
                WHERE industry_id = ? AND effective_to IS NULL
                ORDER BY instrument_id
            """
            params = [industry_id]

        # 执行查询
        rows = self._client.fetchall(sql, params)
        result = [int(r["instrument_id"]) for r in rows]

        # 缓存结果
        self._cache.set(cache_key, result)

        return result

    @traced("data.industry.get_stock_industry")
    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        获取股票所属行业.

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-time 查询日期，None 表示查询当前.

        Returns:
            行业映射信息字典，如果不存在返回 None.

        """
        # 尝试从缓存获取
        cache_key = f"industry:mapping:stock:{instrument_id}:asof={asof}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建 SQL 查询
        if asof:
            sql = """
                SELECT * FROM industry_mapping
                WHERE instrument_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1
            """
            params = [instrument_id, asof, asof]
        else:
            sql = """
                SELECT * FROM industry_mapping
                WHERE instrument_id = ? AND effective_to IS NULL
            """
            params = [instrument_id]

        # 执行查询
        result = self._client.fetchone(sql, params)

        # 缓存结果
        if result is not None:
            self._cache.set(cache_key, result)

        return result

    @traced("data.industry.get_stock_industries_all_levels")
    def get_stock_industries_all_levels(
        self,
        instrument_id: int,
        asof: str | None = None,
        source: str = "sw",
    ) -> list[dict[str, Any]]:
        """
        获取股票所有级别的行业分类.

        JOIN industry_basic 获取 industry_level，按 level 排序。

        Args:
            instrument_id: 证券 ID.
            asof: Point-in-Time 查询日期，None 表示查询当前.
            source: 行业分类来源（sw=申万, csrc=证监会）.

        Returns:
            行业分类列表（按 industry_level 排序）.

        """
        if asof:
            sql = """
                SELECT im.instrument_id, im.industry_id, im.source, im.effective_from,
                       ib.industry_name, ib.industry_level, ib.parent_id
                FROM industry_mapping im
                JOIN industry_basic ib ON im.industry_id = ib.industry_id
                WHERE im.instrument_id = ? AND im.source = ?
                  AND im.effective_from <= ?
                  AND (im.effective_to IS NULL OR im.effective_to > ?)
                ORDER BY ib.industry_level
            """
            params = [instrument_id, source, asof, asof]
        else:
            sql = """
                SELECT im.instrument_id, im.industry_id, im.source, im.effective_from,
                       ib.industry_name, ib.industry_level, ib.parent_id
                FROM industry_mapping im
                JOIN industry_basic ib ON im.industry_id = ib.industry_id
                WHERE im.instrument_id = ? AND im.source = ?
                  AND im.effective_to IS NULL
                ORDER BY ib.industry_level
            """
            params = [instrument_id, source]

        rows = self._client.fetchall(sql, params)
        return [dict(r) for r in rows]
