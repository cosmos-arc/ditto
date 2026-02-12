"""
Index constituent reader for CQRS pattern.

Provides read-only access to index constituent data with PIT support.
Following design document at docs/plans/2026-02-09-datahub-cqrs-refactor.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndexConstituentReader:
    """
    Index constituent data reader.

    Provides read-only access to index constituent data with PIT support.
    Uses SQLiteStore for all data operations.

    Storage structure:
        data_root/
            market/index/constituent.db

    Table schema:
        CREATE TABLE index_constituent (
            index_instrument_id INTEGER NOT NULL,
            constituent_instrument_id INTEGER NOT NULL,
            effective_date TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (index_instrument_id, constituent_instrument_id, effective_date)
        )

    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize IndexConstituentReader.

        Args:
            data_root: Root directory for data storage.

        """
        db_path = data_root / "market" / "index" / "constituent.db"
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = SQLiteStore(db_path)
        self._table = "index_constituent"
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create table if not exists."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS index_constituent (
            index_instrument_id INTEGER NOT NULL,
            constituent_instrument_id INTEGER NOT NULL,
            effective_date TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (index_instrument_id, constituent_instrument_id, effective_date)
        )
        """
        self._store.execute(create_sql)
        self._store.commit()

    # ============ Read operations ============

    @traced("data.read")
    def read(
        self,
        index_instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Read index constituent data.

        Args:
            index_instrument_ids: Filter by index instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with matching records.

        """
        # Build SQL query with correct column names
        conditions: list[str] = []
        params: list[str | int] = []

        if index_instrument_ids:
            placeholders = ",".join("?" * len(index_instrument_ids))
            conditions.append(f"index_instrument_id IN ({placeholders})")
            params.extend(index_instrument_ids)

        if start_date:
            conditions.append("effective_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("effective_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = f"SELECT * FROM {self._table}{where_clause}"  # noqa: S608 - self._table is controlled

        # Execute query
        rows = self._store.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        df = pl.DataFrame(rows)

        # Normalize effective_date from string to Date
        if "effective_date" in df.columns and df["effective_date"].dtype == pl.String:
            df = df.with_columns(
                pl.col("effective_date").str.strptime(pl.Date, "%Y-%m-%d")
            )

        return df

    @traced("data.read")
    def get(self, index_instrument_id: int, asof: str) -> pl.DataFrame:
        """
        Get index constituents as of a specific date (Point-in-Time).

        This implements PIT logic: for each
        (index_instrument_id, constituent_instrument_id) pair, select the
        record with the latest effective_date <= asof date.

        Args:
            index_instrument_id: Index instrument ID.
            asof: As-of date (YYYY-MM-DD).

        Returns:
            DataFrame with constituent stocks as of the specified date.
            Columns:
                index_instrument_id, constituent_instrument_id,
                effective_date, weight

        """
        # Build SQL query with PIT logic
        sql = """
        SELECT
            ic.index_instrument_id,
            ic.constituent_instrument_id,
            ic.effective_date,
            ic.weight
        FROM index_constituent ic
        INNER JOIN (
            SELECT
                constituent_instrument_id,
                MAX(effective_date) as max_effective_date
            FROM index_constituent
            WHERE index_instrument_id = ?
              AND effective_date <= ?
            GROUP BY constituent_instrument_id
        ) latest
        ON ic.constituent_instrument_id = latest.constituent_instrument_id
        AND ic.effective_date = latest.max_effective_date
        WHERE ic.index_instrument_id = ?
        ORDER BY ic.constituent_instrument_id
        """

        params = [index_instrument_id, asof, index_instrument_id]
        rows = self._store.fetchall(sql, params)

        if not rows:
            return pl.DataFrame(
                schema={
                    "index_instrument_id": pl.Int64,
                    "constituent_instrument_id": pl.Int64,
                    "effective_date": pl.String,
                    "weight": pl.Float64,
                }
            )

        df = pl.DataFrame(rows)

        # Normalize effective_date from string to Date
        if "effective_date" in df.columns and df["effective_date"].dtype == pl.String:
            df = df.with_columns(
                pl.col("effective_date").str.strptime(pl.Date, "%Y-%m-%d")
            )

        logger.info(
            "Index constituents retrieved",
            event="pit_query_complete",
            index_instrument_id=index_instrument_id,
            asof=asof,
            constituent_count=len(df),
        )

        return df

    def count(
        self,
        index_instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Count index constituent records.

        Args:
            index_instrument_ids: Filter by index instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of matching records.

        """
        df = self.read(
            index_instrument_ids=index_instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )
        return len(df)

    @property
    def data_root(self) -> Path:
        """
        Get the data root directory.

        Returns:
            Data root directory path.

        """
        return self._store.data_root
