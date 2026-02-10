# pyright: reportPrivateUsage=false
"""InstrumentReader - 证券主数据查询接口."""

from __future__ import annotations

from typing import Any, cast

import polars as pl
from ditto_foundation import logger


def _build_in_clause(
    column: str,
    items: list[Any],
    chunk_size: int = 200,
) -> tuple[str, list[Any]]:
    """
    构建参数化 IN 子句（自动分块）。

    确保 SQL 注入安全，使用参数化查询。
    当列表超过 chunk_size 时，自动分块并用 OR 连接。

    Args:
        column: 列名（如 "s.instrument_id", "m.source_ticker"）。
        items: 值列表。
        chunk_size: 每块的最大参数数量（默认 200，SQLite 限制）。

    Returns:
        (sql_clause, params) 元组：
        - sql_clause: IN 子句 SQL 片段
        - params: 参数列表

    Examples:
        >>> _build_in_clause("s.instrument_id", [1, 2, 3])
        ("s.instrument_id IN (?,?,?)", [1, 2, 3])
        >>> _build_in_clause("s.instrument_id", [], 200)
        ("1=0", [])
        >>> # 分块处理（超过 chunk_size）  # noqa: E501
        >>> _build_in_clause("s.instrument_id", list(range(500)), 200)
        ("(...)", [...])

    """
    if not items:
        return ("1=0", [])  # 空 IN 返回 False 条件

    if len(items) <= chunk_size:
        placeholders = ",".join("?" * len(items))
        in_clause = column + " IN (" + placeholders + ")"
        return (in_clause, items)

    # 分块处理：用 OR 连接多个 IN 子句
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
    clauses: list[str] = []
    params: list[Any] = []
    for chunk in chunks:
        placeholders = ",".join("?" * len(chunk))
        in_clause = column + " IN (" + placeholders + ")"
        clauses.append(in_clause)
        params.extend(chunk)

    clause = "(" + " OR ".join(clauses) + ")"
    return (clause, params)


class InstrumentReader:
    """
    证券主数据查询接口。

    提供：
    - resolve_instrument_id() - 根据 source_ticker 解析 instrument_id
      （支持 PIT + DataCache）
    - resolve_instrument_ids_batch() - 批量解析（优化的单次查询）
    - get_source_ticker() - 反向查询（支持 PIT）
    - get_instrument_id_symbol_map() - 批量获取 symbol 映射
      （支持 DataCache）
    - find_securities() - 带过滤条件的查询
    - list_instrument_ids() - 列出所有 instrument_id
    - get_symbol() - 获取单个 symbol

    Attributes:
        _client: SQLite 客户端，用于数据库访问
        _cache: DataCache 缓存管理器（可选）

    """

    def __init__(self, client: Any, cache: Any | None = None) -> None:
        """
        初始化 InstrumentReader。

        Args:
            client: SQLite 客户端实例
            cache: 可选的 DataCache 实例

        """
        self._client = client
        self._cache = cache
        logger.debug(
            "InstrumentReader initialized",
            event="instrument_reader_init_complete",
        )

    def resolve_instrument_id(
        self,
        source_ticker: str,
        source: str,
        asof: str | None = None,
    ) -> int | None:
        """
        解析 source_ticker 为 instrument_id（支持 PIT）。

        Args:
            source_ticker: 源代码，如 "600000.SH"
            source: 数据源标识符
            asof: Point-in-Time 日期，None 表示当前

        Returns:
            instrument_id 或 None（未找到时）

        """
        logger.debug(
            "Starting Instrument ID resolution",
            event="instrument_id_resolve_start",
            source_ticker=source_ticker,
            source=source,
            asof=asof,
        )

        # 尝试从 DataCache 获取
        if self._cache:
            cache_key = f"instrument_id:{source_ticker}:{source}:{asof or 'current'}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached if cached != -1 else None

        # 从数据库查询
        result = self._resolve_from_db(source_ticker, source, asof)

        # 缓存结果（使用 -1 表示 None）
        if self._cache:
            cache_key = f"instrument_id:{source_ticker}:{source}:{asof or 'current'}"
            self._cache.set(cache_key, result if result is not None else -1)

        return result

    def _resolve_from_db(
        self,
        source_ticker: str,
        source: str,
        asof: str | None = None,
    ) -> int | None:
        """从数据库解析 instrument_id。"""
        if asof:
            # PIT 查询
            row = self._client.fetchone(
                """SELECT instrument_id FROM instrument_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, source_ticker, asof, asof],
            )
        else:
            # 当前查询（更快）
            row = self._client.fetchone(
                """SELECT instrument_id FROM instrument_mapping
                WHERE source = ? AND source_ticker = ?
                  AND effective_to IS NULL""",
                [source, source_ticker],
            )

        return cast(int, row["instrument_id"]) if row else None

    def resolve_instrument_ids_batch(
        self,
        source_tickers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        批量解析 source_tickers 为 instrument_ids。

        使用单次 SQL 查询以获得更好的性能（O(1) 而非 O(n)）。

        Args:
            source_tickers: 源代码列表
            source: 数据源标识符
            asof: Point-in-Time 日期

        Returns:
            source_ticker 到 instrument_id 的映射（仅包含找到的代码）

        """
        logger.info(
            "Starting batch Instrument ID resolution",
            event="instrument_id_batch_resolve_start",
            source=source,
            asof=asof,
            input_count=len(source_tickers),
        )

        if not source_tickers:
            return {}

        # 构建参数化 IN 子句
        in_clause, params = _build_in_clause("source_ticker", source_tickers)
        sql = f"""
            SELECT source_ticker, instrument_id
            FROM instrument_mapping
            WHERE source = ? AND {in_clause}
        """  # noqa: S608 - in_clause 通过 _build_in_clause 安全构建
        query_params = [source, *params]

        if asof:
            sql += (
                " AND effective_from <= ? "
                "AND (effective_to IS NULL OR effective_to > ?)"
            )
            query_params.extend([asof, asof])
        else:
            sql += " AND effective_to IS NULL"

        rows = self._client.fetchall(sql, query_params)
        result = {
            cast(str, r["source_ticker"]): cast(int, r["instrument_id"]) for r in rows
        }

        logger.info(
            "Batch Instrument ID resolution completed",
            event="instrument_id_batch_resolve_complete",
            requested=len(source_tickers),
            found=len(result),
            not_found=len(source_tickers) - len(result),
        )

        return result

    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        反向查询：instrument_id 到 source_ticker。

        Args:
            instrument_id: 证券 ID
            source: 数据源标识符
            asof: Point-in-Time 日期

        Returns:
            source_ticker 或 None（未找到时）

        """
        if asof:
            row = self._client.fetchone(
                """SELECT source_ticker FROM instrument_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [instrument_id, source, asof, asof],
            )
        else:
            row = self._client.fetchone(
                """SELECT source_ticker FROM instrument_mapping
                WHERE instrument_id = ? AND source = ?
                  AND effective_to IS NULL""",
                [instrument_id, source],
            )

        return cast(str, row["source_ticker"]) if row else None

    def find_securities(
        self,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        带过滤条件查询证券。

        Args:
            instrument_ids: 按 instrument_ids 过滤
            source_tickers: 按源代码过滤
            source: 数据源标识符
            asset_class: 按资产类别过滤
            exchange: 按交易所过滤
            is_active: 按活跃状态过滤
            asof: Point-in-Time 日期

        Returns:
            包含证券数据的 DataFrame

        """
        sql = """
            SELECT s.*, m.source, m.source_ticker
            FROM instrument s
            LEFT JOIN instrument_mapping m ON s.instrument_id = m.instrument_id
            WHERE 1=1
        """
        params: list[Any] = []

        if instrument_ids:
            in_clause, sids_list = _build_in_clause("s.instrument_id", instrument_ids)
            sql += f" AND {in_clause}"
            params.extend(sids_list)

        if source_tickers:
            in_clause, source_tickers_list = _build_in_clause(
                "m.source_ticker", source_tickers
            )
            sql += f" AND {in_clause} AND m.source = ?"
            params.extend(source_tickers_list)
            params.append(source)

            if asof:
                sql += (
                    " AND m.effective_from <= ? AND "
                    "(m.effective_to IS NULL OR m.effective_to > ?)"
                )
                params.extend([asof, asof])
            else:
                sql += " AND m.effective_to IS NULL"

        if asset_class:
            sql += " AND s.asset_class = ?"
            params.append(asset_class)

        if exchange:
            sql += " AND s.exchange = ?"
            params.append(exchange)

        if is_active is not None:
            sql += " AND s.is_active = ?"
            params.append(is_active)

        rows = self._client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    def list_instrument_ids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
    ) -> list[int]:
        """
        列出所有 instrument_id（可选过滤）。

        Args:
            asset_class: 按资产类别过滤
            exchange: 按交易所过滤
            is_active: 按活跃状态过滤

        Returns:
            instrument_id 列表

        """
        sql = "SELECT instrument_id FROM instrument WHERE 1=1"
        params: list[Any] = []

        if asset_class:
            sql += " AND asset_class = ?"
            params.append(asset_class)

        if exchange:
            sql += " AND exchange = ?"
            params.append(exchange)

        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(is_active)

        rows = self._client.fetchall(sql, params)
        return [cast(int, r["instrument_id"]) for r in rows]

    def get_symbol(self, instrument_id: int) -> str | None:
        """
        获取 symbol。

        Args:
            instrument_id: 证券 ID

        Returns:
            symbol 或 None（未找到时）

        """
        row = self._client.fetchone(
            "SELECT symbol FROM instrument WHERE instrument_id = ?", [instrument_id]
        )
        return cast(str, row["symbol"]) if row else None

    def get_instrument_id_symbol_map(
        self, instrument_ids: list[int] | None = None
    ) -> dict[int, str]:
        """
        批量获取 instrument_id 到 symbol 的映射。

        Args:
            instrument_ids: 要查询的 instrument_id 列表，None 表示所有活跃的

        Returns:
            instrument_id 到 symbol 的映射字典

        """
        # 尝试从 DataCache 获取
        if self._cache and instrument_ids:
            # 使用排序后的 tuple 作为缓存键
            cache_key = (
                f"instrument_id_symbol_map:{','.join(map(str, sorted(instrument_ids)))}"
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cast(dict[int, str], cached)

        # 从数据库查询
        if instrument_ids:
            in_clause, sids_list = _build_in_clause("instrument_id", instrument_ids)
            rows = self._client.fetchall(
                f"SELECT instrument_id, symbol FROM instrument WHERE {in_clause}",  # noqa: S608 - in_clause 通过 _build_in_clause 安全构建
                sids_list,
            )
        else:
            rows = self._client.fetchall(
                "SELECT instrument_id, symbol FROM instrument WHERE is_active = TRUE"
            )

        result = {cast(int, r["instrument_id"]): cast(str, r["symbol"]) for r in rows}

        # 缓存结果
        if self._cache and instrument_ids:
            cache_key = (
                f"instrument_id_symbol_map:{','.join(map(str, sorted(instrument_ids)))}"
            )
            self._cache.set(cache_key, result)

        return result
