"""UniverseReader - 证券域查询接口."""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_platform.foundation import DataCache, SQLiteClient, logger


class UniverseReader:
    """
    证券域查询接口。

    提供：
    - get_universe() - 获取单个证券域定义
    - list_universes() - 列出所有证券域
    - get_constituents() - 获取成分股（支持 PIT）
    - get_constituent_instrument_ids() - 获取成分股 ID 列表（支持 PIT）

    Attributes:
        _client: SQLite 客户端，用于数据库访问
        _cache: 缓存管理器，用于查询结果缓存

    """

    def __init__(self, client: SQLiteClient, cache: DataCache[Any]) -> None:
        """
        初始化 UniverseReader。

        Args:
            client: SQLite 客户端实例
            cache: 缓存管理器实例

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "UniverseReader initialized",
            event="universe_reader_init_complete",
        )

    def get_universe(self, universe_id: str) -> dict[str, Any] | None:
        """
        获取证券域定义。

        Args:
            universe_id: 证券域 ID

        Returns:
            证券域数据字典，不存在时返回 None

        """
        cache_key = f"universe:{universe_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        row = self._client.fetchone(
            "SELECT * FROM universe WHERE universe_id = ?",
            [universe_id],
        )

        if row is not None:
            self._cache.set(cache_key, row)

        return row

    def list_universes(self, universe_type: str | None = None) -> pl.DataFrame:
        """
        列出所有证券域。

        Args:
            universe_type: 可选的类型过滤器

        Returns:
            包含证券域数据的 DataFrame

        """
        sql = "SELECT * FROM universe"
        params: list[Any] = []

        if universe_type:
            sql += " WHERE universe_type = ?"
            params.append(universe_type)

        rows = self._client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame(rows)

    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        获取证券域成分股（PIT 安全）。

        Args:
            universe_id: 证券域 ID
            asof: Point-in-Time 日期，None 表示当前

        Returns:
            包含成分股数据的 DataFrame

        """
        if asof:
            # PIT 查询
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY instrument_id""",
                [universe_id, asof, asof],
            )
        else:
            # 当前查询
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ? AND effective_to IS NULL
                ORDER BY instrument_id""",
                [universe_id],
            )

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame(rows)

    def get_constituent_instrument_ids(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取成分股 instrument_id 列表。

        Args:
            universe_id: 证券域 ID
            asof: Point-in-Time 日期，None 表示当前

        Returns:
            instrument_id 列表

        """
        df = self.get_constituents(universe_id, asof)
        return df["instrument_id"].to_list() if not df.is_empty() else []
