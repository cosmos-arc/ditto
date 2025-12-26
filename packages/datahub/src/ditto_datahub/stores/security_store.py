"""
SecurityStore for securities master data with PIT support.

This module provides storage and retrieval for securities master data
with Point-in-Time support for identifier resolution.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, cast

import polars as pl
from ditto_foundation import M, logger, span, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


def _build_in_clause(items: list[Any]) -> tuple[str, list[Any]]:
    """
    Build parameterized IN clause with placeholders.

    This helper function ensures SQL injection safety by using
    parameterized queries for IN clauses.

    Args:
        items: List of values for the IN clause.

    Returns:
        Tuple of (SQL fragment with placeholders, list of values).

    Example:
        >>> _build_in_clause([1, 2, 3])
        ('(?,?,?)', [1, 2, 3])

    """
    if not items:
        return ("()", [])
    placeholders = ",".join("?" * len(items))
    return f"({placeholders})", items


class SecurityStore:
    """
    Securities master data storage with PIT support.

    Core functionality:
    - resolve_sid: (source, src_code, asof) -> sid
    - Through security_mapping with effective_from/to for historical resolution
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize SecurityStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    @lru_cache(maxsize=10000)  # noqa: B019 - cache is safe for stateless lookup
    def resolve_sid_cached(self, src_code: str, source: str) -> int | None:
        """
        Cache current mapping (for queries without asof).

        Args:
            src_code: Source code.
            source: Data source identifier.

        Returns:
            sid or None if not found.

        """
        return self._resolve_sid_from_db(src_code, source, asof=None)

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

        if asof is None:
            result = self.resolve_sid_cached(src_code, source)
        else:
            result = self._resolve_sid_from_db(src_code, source, asof)

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
            in_clause, sids_list = _build_in_clause(sids)
            sql += f" AND s.sid IN {in_clause}"
            params.extend(sids_list)

        if src_codes:
            in_clause, src_codes_list = _build_in_clause(src_codes)
            sql += f" AND m.src_code IN {in_clause} AND m.source = ?"
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
        is_active: bool = True,
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
        if sids:
            in_clause, sids_list = _build_in_clause(sids)
            rows = self._client.fetchall(
                f"SELECT sid, symbol FROM security WHERE sid IN {in_clause}",
                sids_list,
            )
        else:
            rows = self._client.fetchall(
                "SELECT sid, symbol FROM security WHERE is_active = TRUE"
            )

        return {cast(int, r["sid"]): cast(str, r["symbol"]) for r in rows}

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

        return df.join(symbol_df, on="sid", how="left")

    def register(
        self,
        sid: int,
        source: str,
        src_code: str,
        symbol: str,
        name: str,
        exchange: str,
        asset_class: str,
        list_date: str,
        board: str | None = None,
    ) -> int:
        """
        Register a new security.

        Args:
            sid: Security ID.
            source: Data source identifier.
            src_code: Source code.
            symbol: Display symbol.
            name: Security name.
            exchange: Exchange code.
            asset_class: Asset class.
            list_date: Listing date.
            board: Board code (optional).

        Returns:
            The registered sid.

        """
        logger.info(
            "Starting security registration",
            event="security_register_start",
            sid=sid,
            symbol=symbol,
            src_code=src_code,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
        )

        try:
            # Insert into security table
            self._client.execute(
                """INSERT INTO security
                (sid, symbol, name, exchange, board, asset_class, list_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, TRUE)""",
                [sid, symbol, name, exchange, board, asset_class, list_date],
            )

            # Insert into mapping table
            self._client.execute(
                """INSERT INTO security_mapping
                (sid, source, src_code, effective_from, is_primary)
                VALUES (?, ?, ?, ?, TRUE)""",
                [sid, source, src_code, list_date],
            )

            self._client.commit()

            logger.info(
                "Security registered successfully",
                event="security_register_complete",
                sid=sid,
                symbol=symbol,
            )

            return sid

        except Exception:
            self._client.rollback()
            logger.error(
                "Security registration failed",
                event="security_register_failed",
                sid=sid,
                symbol=symbol,
            )
            raise
