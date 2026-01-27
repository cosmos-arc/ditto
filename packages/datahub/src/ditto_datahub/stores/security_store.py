"""
SecurityStore for securities master data with PIT support.

This module provides storage and retrieval for securities master data
with Point-in-Time support for identifier resolution.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.cache import DataCache

from ditto_datahub.accessors.internal.enrichment import (
    enrich_with_symbol as enrich_with_symbol_fn,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient


@dataclass(frozen=True)
class SecurityRegistration:
    """
    证券注册信息配置对象。

    用于封装证券注册所需的所有参数，避免函数参数过多。
    """

    src_code: str
    symbol: str
    name: str
    exchange: str
    asset_class: str
    list_date: str
    source: str = "tushare"
    board: str | None = None


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
        column: 列名（如 "s.sid", "m.src_code"）。
        items: 值列表。
        chunk_size: 每块的最大参数数量（默认 200，SQLite 限制）。

    Returns:
        (SQL 片段, 参数列表) 元组。

    Examples:
        >>> _build_in_clause("s.sid", [1, 2, 3])
        ('s.sid IN (?,?,?)', [1, 2, 3])
        >>> _build_in_clause("s.sid", list(range(500)), chunk_size=200)
        ('(s.sid IN (...)) OR (s.sid IN (...))', [...])

    """
    if not items:
        return ("1=0", [])  # 空 IN 返回 False 条件

    if len(items) <= chunk_size:
        placeholders = ",".join("?" * len(items))
        return f"{column} IN ({placeholders})", items

    # 分块处理：用 OR 连接多个 IN 子句
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
    clauses: list[str] = []
    params: list[Any] = []
    for chunk in chunks:
        placeholders = ",".join("?" * len(chunk))
        clauses.append(f"{column} IN ({placeholders})")
        params.extend(chunk)

    return f"({' OR '.join(clauses)})", params


class SecurityStore:
    """
    Securities master data storage with PIT support.

    Core functionality:
    - resolve_sid: (source, src_code, asof) -> sid
    - Through security_mapping with effective_from/to for historical resolution

    Note: SecurityStore does not inherit SQLiteStore as it uses SQLiteClient
    for data access to maintain backward compatibility. Future versions may
    refactor to directly inherit SQLiteStore.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any] | None = None,
    ) -> None:
        """
        Initialize SecurityStore.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: Optional DataCache for SID resolution caching.

        """
        self._client = sqlite_client
        self._data_cache = data_cache

    @traced("data.sid_resolve")
    def resolve_sid(self, src_code: str, source: str, asof: str | None) -> int | None:
        """
        Resolve src_code to sid (with PIT support).

        Args:
            src_code: Source code like "600000.SH".
            source: Data source identifier.
            asof: Point-in-time date, None for current.

        Returns:
            sid or None if not found.

        """
        logger.debug(
            "Starting SID resolution",
            event="sid_resolve_start",
            src_code=src_code,
            source=source,
            asof=asof,
        )

        # 尝试从 DataCache 获取
        if self._data_cache:
            cache_key = f"sid:{src_code}:{source}:{asof or 'current'}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return cached if cached != -1 else None

        # 从数据库查询
        result = self._resolve_sid_from_db(src_code, source, asof)

        # 缓存结果（使用 -1 表示 None）
        if self._data_cache:
            cache_key = f"sid:{src_code}:{source}:{asof or 'current'}"
            self._data_cache.set(cache_key, result if result is not None else -1)

        if result:
            logger.debug(
                "SID resolved successfully",
                event="sid_resolve_complete",
                src_code=src_code,
                sid=result,
            )
            # Record metrics
            M.data_records.add(1, {"dataset": "sid_resolution", "status": "success"})
        else:
            logger.warning(
                "SID not found",
                event="sid_resolve_not_found",
                src_code=src_code,
                source=source,
                asof=asof,
            )
            # Record metrics
            M.data_records.add(1, {"dataset": "sid_resolution", "status": "not_found"})

        return result

    def _resolve_sid_from_db(
        self,
        src_code: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        Resolve src_code to sid (with PIT support).

        Args:
            src_code: Source code like "600000.SH".
            source: Data source identifier.
            asof: Point-in-time date, None for current.

        """
        if asof:
            # PIT mode: query historical mapping
            row = self._client.fetchone(
                """SELECT sid FROM security_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, src_code, asof, asof],
            )
        else:
            # Current mode: only query active mapping (faster)
            row = self._client.fetchone(
                """SELECT sid FROM security_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_to IS NULL""",
                [source, src_code],
            )

        return cast(int, row["sid"]) if row else None

    def resolve_sids_batch(
        self,
        src_codes: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        Batch resolve src_codes to sids.

        Args:
            src_codes: List of source codes.
            source: Data source identifier.
            asof: Point-in-time date.

        Returns:
            Dictionary mapping src_code to sid (only for found codes).

        """
        logger.info(
            "Starting batch SID resolution",
            event="sid_batch_resolve_start",
            source=source,
            asof=asof,
            input_count=len(src_codes),
        )

        result: dict[str, int] = {}
        for code in src_codes:
            sid = self.resolve_sid(code, source, asof)
            if sid:
                result[code] = sid

        logger.info(
            "Batch SID resolution completed",
            event="sid_batch_resolve_complete",
            requested=len(src_codes),
            found=len(result),
            not_found=len(src_codes) - len(result),
        )

        return result

    def resolve_by_symbol(
        self,
        symbol: str,
        source: str = "tushare",
    ) -> list[int]:
        """
        Query sids by symbol (may have multiple results).

        Args:
            symbol: Display symbol.
            source: Data source identifier.

        Returns:
            List of sids.

        """
        rows = self._client.fetchall(
            """SELECT DISTINCT s.sid
            FROM security s
            JOIN security_mapping m ON s.sid = m.sid
            WHERE s.symbol = ? AND m.source = ? AND m.effective_to IS NULL""",
            [symbol, source],
        )
        return [cast(int, r["sid"]) for r in rows]

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        Reverse lookup: sid to src_code.

        Args:
            sid: Security ID.
            source: Data source identifier.
            asof: Point-in-time date.

        Returns:
            src_code or None if not found.

        """
        if asof:
            row = self._client.fetchone(
                """SELECT src_code FROM security_mapping
                WHERE sid = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [sid, source, asof, asof],
            )
        else:
            row = self._client.fetchone(
                """SELECT src_code FROM security_mapping
                WHERE sid = ? AND source = ?
                  AND effective_to IS NULL""",
                [sid, source],
            )

        return cast(str, row["src_code"]) if row else None

    def get_by_sid(self, sid: int) -> dict[str, Any] | None:
        """
        Get security by sid.

        Args:
            sid: Security ID.

        Returns:
            Dictionary with security data or None.

        """
        row = self._client.fetchone("SELECT * FROM security WHERE sid = ?", [sid])
        return row

    def find_securities(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Query securities with filters.

        Args:
            sids: Filter by sids.
            src_codes: Filter by source codes.
            source: Data source identifier.
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.
            asof: Point-in-time date.

        Returns:
            DataFrame with securities data.

        """
        sql = """
            SELECT s.*, m.source, m.src_code
            FROM security s
            LEFT JOIN security_mapping m ON s.sid = m.sid
            WHERE 1=1
        """
        params: list[Any] = []

        if sids:
            in_clause, sids_list = _build_in_clause("s.sid", sids)
            sql += f" AND {in_clause}"
            params.extend(sids_list)

        if src_codes:
            in_clause, src_codes_list = _build_in_clause("m.src_code", src_codes)
            sql += f" AND {in_clause} AND m.source = ?"
            params.extend(src_codes_list)
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

    def list_sids(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
    ) -> list[int]:
        """
        List all sids with optional filters.

        Args:
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.

        Returns:
            List of sids.

        """
        sql = "SELECT sid FROM security WHERE 1=1"
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
        return [cast(int, r["sid"]) for r in rows]

    def get_symbol(self, sid: int) -> str | None:
        """
        Get symbol by sid.

        Args:
            sid: Security ID.

        Returns:
            Symbol or None if not found.

        """
        row = self._client.fetchone("SELECT symbol FROM security WHERE sid = ?", [sid])
        return cast(str, row["symbol"]) if row else None

    def get_sid_symbol_map(self, sids: list[int] | None = None) -> dict[int, str]:
        """
        Get batch sid to symbol mapping.

        Args:
            sids: List of sids to query, None for all active.

        Returns:
            Dictionary mapping sid to symbol.

        """
        # 尝试从 DataCache 获取
        if self._data_cache and sids:
            # 使用排序后的 tuple 作为缓存键
            cache_key = f"sid_symbol_map:{','.join(map(str, sorted(sids)))}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return cast(dict[int, str], cached)

        # 从数据库查询
        if sids:
            in_clause, sids_list = _build_in_clause("sid", sids)
            rows = self._client.fetchall(
                f"SELECT sid, symbol FROM security WHERE {in_clause}",  # noqa: S608 - in_clause 通过 _build_in_clause 安全构建
                sids_list,
            )
        else:
            rows = self._client.fetchall(
                "SELECT sid, symbol FROM security WHERE is_active = TRUE"
            )

        result = {cast(int, r["sid"]): cast(str, r["symbol"]) for r in rows}

        # 缓存结果
        if self._data_cache and sids:
            cache_key = f"sid_symbol_map:{','.join(map(str, sorted(sids)))}"
            self._data_cache.set(cache_key, result)

        return result

    def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Add symbol column to DataFrame.

        Args:
            df: DataFrame with sid column.

        Returns:
            DataFrame with symbol column added.

        """
        if "sid" not in df.columns or df.is_empty():
            return df

        sids = df["sid"].unique().to_list()
        symbol_map = self.get_sid_symbol_map(sids)

        symbol_df = pl.DataFrame(
            {
                "sid": list(symbol_map.keys()),
                "symbol": list(symbol_map.values()),
            }
        )

        # 使用纯函数进行数据增强
        return enrich_with_symbol_fn(df, symbol_df)

    def register(self, sid: int, registration: SecurityRegistration) -> int:
        """
        Register a new security.

        Args:
            sid: Security ID.
            registration: Security registration configuration.

        Returns:
            The registered sid.

        """
        logger.info(
            "Starting security registration",
            event="security_register_start",
            sid=sid,
            symbol=registration.symbol,
            src_code=registration.src_code,
            source=registration.source,
            asset_class=registration.asset_class,
            exchange=registration.exchange,
        )

        try:
            # Insert into security table
            self._client.execute(
                """INSERT INTO security
                (sid, symbol, name, exchange, board, asset_class, list_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
                [
                    sid,
                    registration.symbol,
                    registration.name,
                    registration.exchange,
                    registration.board,
                    registration.asset_class,
                    registration.list_date,
                ],
            )

            # Insert into mapping table
            self._client.execute(
                """INSERT INTO security_mapping
                (sid, source, src_code, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)""",
                [
                    sid,
                    registration.source,
                    registration.src_code,
                    registration.list_date,
                ],
            )

            # 失效相关缓存
            if self._data_cache:
                # 失效特定 src_code 的负缓存（如果有）
                cache_key = f"sid:{registration.src_code}:{registration.source}:current"
                self._data_cache.invalidate(cache_key)
                # 失效 sid_symbol_map 缓存
                self._data_cache.invalidate_pattern("sid_symbol_map:*")

            self._client.commit()

            logger.info(
                "Security registered successfully",
                event="security_register_complete",
                sid=sid,
                symbol=registration.symbol,
            )

            return sid

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Security registration failed",
                event="security_register_failed",
                sid=sid,
                symbol=registration.symbol,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
