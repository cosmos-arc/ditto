"""
InstrumentStore for instruments master data with PIT support.

This module provides storage and retrieval for instruments master data
with Point-in-Time support for identifier resolution.

命名映射：
- Python 代码使用 instrument/source_ticker
- 数据库表/列保持 instrument/source_ticker（避免数据迁移）

Migration: 重构自 SecurityStore (2026-01-29)
"""

from __future__ import annotations

from typing import Any, cast

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.cache import DataCache

from ditto_datahub.stores.metadata.instrument.models import InstrumentRegistration
from ditto_datahub.stores.sqlite_client import SQLiteClient


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
        (SQL 片段, 参数列表) 元组。

    Examples:
        >>> _build_in_clause("s.instrument_id", [1, 2, 3])
        ('s.instrument_id IN (?,?,?)', [1, 2, 3])
        >>> _build_in_clause("s.instrument_id", list(range(500)), chunk_size=200)
        ('(s.instrument_id IN (...)) OR (s.instrument_id IN (...))', [...])

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


class InstrumentStore:
    """
    Instruments master data storage with PIT support.

    Core functionality:
    - resolve_instrument_id: (source, source_ticker, asof) -> instrument_id
    - 通过 instrument_mapping 表（数据库保持原名）的 effective_from/to 实现 PIT 查询

    Note: InstrumentStore does not inherit SQLiteStore as it uses SQLiteClient
    for data access to maintain backward compatibility. Future versions may
    refactor to directly inherit SQLiteStore.

    命名映射：
    - Python 代码使用 instrument/source_ticker
    - 数据库表/列保持 instrument/source_ticker（避免数据迁移）

    Migration: 重构自 SecurityStore (2026-01-29)
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any] | None = None,
    ) -> None:
        """
        Initialize InstrumentStore.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: Optional DataCache for instrument_id resolution caching.

        """
        self._client = sqlite_client
        self._data_cache = data_cache

    @traced("data.instrument_id_resolve")
    def resolve_instrument_id(
        self, source_ticker: str, source: str, asof: str | None
    ) -> int | None:
        """
        Resolve source_ticker to instrument_id (with PIT support).

        Args:
            source_ticker: Source code like "600000.SH".
            source: Data source identifier.
            asof: Point-in-time date, None for current.

        Returns:
            instrument_id or None if not found.

        """
        logger.debug(
            "Starting Instrument ID resolution",
            event="instrument_id_resolve_start",
            source_ticker=source_ticker,
            source=source,
            asof=asof,
        )

        # 尝试从 DataCache 获取
        if self._data_cache:
            cache_key = f"instrument_id:{source_ticker}:{source}:{asof or 'current'}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return cached if cached != -1 else None

        # 从数据库查询
        result = self._resolve_instrument_id_from_db(source_ticker, source, asof)

        # 缓存结果（使用 -1 表示 None）
        if self._data_cache:
            cache_key = f"instrument_id:{source_ticker}:{source}:{asof or 'current'}"
            self._data_cache.set(cache_key, result if result is not None else -1)

        if result:
            logger.debug(
                "Instrument ID resolved successfully",
                event="instrument_id_resolve_complete",
                source_ticker=source_ticker,
                instrument_id=result,
            )
            # Record metrics
            M.data_records.add(
                1, {"dataset": "instrument_id_resolution", "status": "success"}
            )
        else:
            logger.warning(
                "Instrument ID not found",
                event="instrument_id_resolve_not_found",
                source_ticker=source_ticker,
                source=source,
                asof=asof,
            )
            # Record metrics
            M.data_records.add(
                1, {"dataset": "instrument_id_resolution", "status": "not_found"}
            )

        return result

    def _resolve_instrument_id_from_db(
        self,
        source_ticker: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        Resolve source_ticker to instrument_id (with PIT support).

        Args:
            source_ticker: Source code like "600000.SH".
            source: Data source identifier.
            asof: Point-in-time date, None for current.

        """
        if asof:
            # PIT mode: query historical mapping
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
            # Current mode: only query active mapping (faster)
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
        Batch resolve source_tickers to instrument_ids.

        Args:
            source_tickers: List of source codes.
            source: Data source identifier.
            asof: Point-in-time date.

        Returns:
            Dictionary mapping source_ticker to instrument_id (only for found codes).

        """
        logger.info(
            "Starting batch Instrument ID resolution",
            event="instrument_id_batch_resolve_start",
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
            "Batch Instrument ID resolution completed",
            event="instrument_id_batch_resolve_complete",
            requested=len(source_tickers),
            found=len(result),
            not_found=len(source_tickers) - len(result),
        )

        return result

    def resolve_by_symbol(
        self,
        symbol: str,
        source: str = "tushare",
    ) -> list[int]:
        """
        Query instrument_ids by symbol (may have multiple results).

        Args:
            symbol: Display symbol.
            source: Data source identifier.

        Returns:
            List of instrument_ids.

        """
        rows = self._client.fetchall(
            """SELECT DISTINCT s.instrument_id
            FROM instrument s
            JOIN instrument_mapping m ON s.instrument_id = m.instrument_id
            WHERE s.symbol = ? AND m.source = ? AND m.effective_to IS NULL""",
            [symbol, source],
        )
        return [cast(int, r["instrument_id"]) for r in rows]

    def get_source_ticker(
        self,
        instrument_id: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        Reverse lookup: instrument_id to source_ticker.

        Args:
            instrument_id: Security ID.
            source: Data source identifier.
            asof: Point-in-time date.

        Returns:
            source_ticker or None if not found.

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

    def get_by_instrument_id(self, instrument_id: int) -> dict[str, Any] | None:
        """
        Get instrument by instrument_id.

        Args:
            instrument_id: Security ID.

        Returns:
            Dictionary with instrument data or None.

        """
        row = self._client.fetchone(
            "SELECT * FROM instrument WHERE instrument_id = ?", [instrument_id]
        )
        return row

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
        Query securities with filters.

        Args:
            instrument_ids: Filter by instrument_ids.
            source_tickers: Filter by source codes.
            source: Data source identifier.
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.
            asof: Point-in-time date.

        Returns:
            DataFrame with securities data.

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
        List all instrument_ids with optional filters.

        Args:
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.

        Returns:
            List of instrument_ids.

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
        Get symbol by instrument_id.

        Args:
            instrument_id: Security ID.

        Returns:
            Symbol or None if not found.

        """
        row = self._client.fetchone(
            "SELECT symbol FROM instrument WHERE instrument_id = ?", [instrument_id]
        )
        return cast(str, row["symbol"]) if row else None

    def get_instrument_id_symbol_map(
        self, instrument_ids: list[int] | None = None
    ) -> dict[int, str]:
        """
        Get batch instrument_id to symbol mapping.

        Args:
            instrument_ids: List of instrument_ids to query, None for all active.

        Returns:
            Dictionary mapping instrument_id to symbol.

        """
        # 尝试从 DataCache 获取
        if self._data_cache and instrument_ids:
            # 使用排序后的 tuple 作为缓存键
            cache_key = (
                f"instrument_id_symbol_map:{','.join(map(str, sorted(instrument_ids)))}"
            )
            cached = self._data_cache.get(cache_key)
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
        if self._data_cache and instrument_ids:
            cache_key = (
                f"instrument_id_symbol_map:{','.join(map(str, sorted(instrument_ids)))}"
            )
            self._data_cache.set(cache_key, result)

        return result

    def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Add symbol column to DataFrame.

        Args:
            df: DataFrame with instrument_id column (also supports instrument_id).

        Returns:
            DataFrame with symbol column added.

        """
        id_col = "instrument_id"
        if id_col not in df.columns or df.is_empty():
            return df

        instrument_ids = df[id_col].unique().to_list()
        symbol_map = self.get_instrument_id_symbol_map(instrument_ids)

        symbol_df = pl.DataFrame(
            {
                id_col: list(symbol_map.keys()),
                "symbol": list(symbol_map.values()),
            }
        )

        # 内联数据增强：join symbol 数据
        return df.join(symbol_df, on=id_col, how="left")

    def register(self, instrument_id: int, registration: InstrumentRegistration) -> int:
        """
        Register a new instrument.

        Args:
            instrument_id: Instrument ID.
            registration: Instrument registration configuration.

        Returns:
            The registered instrument_id.

        """
        logger.info(
            "Starting instrument registration",
            event="instrument_register_start",
            instrument_id=instrument_id,
            symbol=registration.symbol,
            source_ticker=registration.source_ticker,
            source=registration.source,
            asset_class=registration.asset_class,
            exchange=registration.exchange,
        )

        try:
            # Insert into instrument table
            self._client.execute(
                """INSERT INTO instrument
                (
                    instrument_id, symbol, name, exchange, board, asset_class,
                    list_date, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
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
                """INSERT INTO instrument_mapping
                (instrument_id, source, source_ticker, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)""",
                [
                    instrument_id,
                    registration.source,
                    registration.source_ticker,
                    registration.list_date,
                ],
            )

            # 失效相关缓存
            if self._data_cache:
                # 失效特定 source_ticker 的负缓存（如果有）
                cache_key = (
                    f"instrument_id:{registration.source_ticker}:"
                    f"{registration.source}:current"
                )
                self._data_cache.invalidate(cache_key)
                # 失效 instrument_id_symbol_map 缓存
                self._data_cache.invalidate_pattern("instrument_id_symbol_map:*")

            self._client.commit()

            logger.info(
                "Instrument registered successfully",
                event="instrument_register_complete",
                instrument_id=instrument_id,
                symbol=registration.symbol,
            )

            return instrument_id

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Instrument registration failed",
                event="instrument_register_failed",
                instrument_id=instrument_id,
                symbol=registration.symbol,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
