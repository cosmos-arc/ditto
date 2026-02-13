"""
Industry reader for CQRS pattern.

Provides read-only access to industry master data.
Following design document at docs/plans/2026-02-09-datahub-metadata-cqrs-design.md
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_infra.foundation import traced


class IndustryReader:
    """
    申万行业主数据读取器.

    提供行业主数据的只读访问，支持缓存优化。

    Attributes:
        _client: SQLite 客户端，用于数据库访问.
        _cache: 缓存管理器，用于查询结果缓存.

    """

    def __init__(self, client: Any, cache: Any) -> None:
        """
        初始化 IndustryReader.

        Args:
            client: SQLite 客户端实例.
            cache: 缓存管理器实例.

        """
        self._client = client
        self._cache = cache

    @traced("data.industry.get_all")
    def get_all(
        self,
        is_active: bool | None = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        获取所有行业信息.

        Args:
            is_active: 是否只返回活跃行业，None 返回全部.
            industry_level: 行业级别过滤 (L1/L2).

        Returns:
            行业信息 DataFrame. 如果没有数据返回空 DataFrame.

        """
        # 尝试从缓存获取
        cache_key = f"industry:all:active={is_active}:level={industry_level}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 构建查询
        sql = "SELECT * FROM industry_basic WHERE 1=1"
        params: list[Any] = []

        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(1 if is_active else 0)

        if industry_level:
            sql += " AND industry_level = ?"
            params.append(industry_level)

        # 执行查询
        rows = self._client.fetchall(sql, params)

        # 转换为 DataFrame
        result = pl.DataFrame() if not rows else pl.DataFrame(rows)

        # 缓存结果
        self._cache.set(cache_key, result)

        return result

    @traced("data.industry.get_by_id")
    def get_by_id(self, industry_id: str) -> dict[str, Any] | None:
        """
        根据 ID 获取行业信息.

        Args:
            industry_id: 行业 ID.

        Returns:
            行业信息字典，如果不存在返回 None.

        """
        return self._client.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            [industry_id],
        )
