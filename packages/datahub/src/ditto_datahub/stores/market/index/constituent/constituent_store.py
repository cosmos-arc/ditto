"""
Index constituent storage with Point-in-Time support.

Stores index constituent data with effective dates for PIT queries.
Following design document at docs/design/02_data_design.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.io import file_md5

from ditto_datahub.models.storage import WriteResultStore
from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndexConstituentStore(SQLiteStore):
    """
    Index constituent data storage with PIT support.

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

    This store provides Point-in-Time queries to get constituents
    as of a specific date.
    """

    def __init__(self, data_root: Path) -> None:
        """
        Initialize IndexConstituentStore.

        Args:
            data_root: Root directory for data storage.

        """
        db_path = data_root / "market" / "index" / "constituent.db"
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(db_path)
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
        self.execute(create_sql)
        self.commit()

    # ============ Write operations ============

    @traced("data.write")
    def write(self, df: pl.DataFrame) -> WriteResultStore:  # type: ignore[override]
        """
        Write index constituent data.

        Args:
            df: Data to write with columns:
                - index_instrument_id: Index instrument ID
                - constituent_instrument_id: Stock instrument ID
                - effective_date: Effective date (YYYY-MM-DD)
                - weight: Constituent weight

        Returns:
            Write result with statistics.

        """
        # Empty data check
        if len(df) == 0:
            return WriteResultStore(
                file_path=str(self._db_path),
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # Prepare data: ensure effective_date is string for SQLite
        if "effective_date" in df.columns and df["effective_date"].dtype == pl.Date:
            df = df.with_columns(
                pl.col("effective_date").dt.strftime("%Y-%m-%d").alias("effective_date")
            )

        # Sort by key columns
        df = df.sort(
            ["index_instrument_id", "constituent_instrument_id", "effective_date"]
        )

        # Check if table has existing data
        existing_count_sql = f"SELECT COUNT(*) as count FROM {self._table}"  # noqa: S608
        existing_result = self.fetchone(existing_count_sql)
        existing_count = int(existing_result["count"]) if existing_result else 0
        is_merge = existing_count > 0

        added = 0
        updated = 0

        if is_merge:
            # Read existing data
            existing_rows = self.fetchall(
                f"SELECT * FROM {self._table}"  # noqa: S608 - self._table is controlled
            )
            existing_df = (
                pl.DataFrame(existing_rows) if existing_rows else pl.DataFrame()
            )

            # Check for duplicates
            if not existing_df.is_empty():
                key_cols = [
                    "index_instrument_id",
                    "constituent_instrument_id",
                    "effective_date",
                ]
                existing_keys = existing_df.select(key_cols)
                new_keys = df.select(key_cols)

                # Find overlap
                overlap = existing_keys.join(new_keys, on=key_cols, how="inner")
                overlap_count = len(overlap)

                if overlap_count > 0:
                    # Filter out overlapping records from new data
                    # (KEEP_FIRST strategy for constituents)
                    non_overlap = new_keys.join(existing_keys, on=key_cols, how="anti")
                    df_to_add = df.join(non_overlap, on=key_cols, how="inner")
                    # Merge existing data with new non-overlapping data
                    df = pl.concat([existing_df, df_to_add], how="diagonal_relaxed")
                    added = len(df_to_add)
                    updated = 0
                else:
                    # No overlap, merge all data
                    df = pl.concat([existing_df, df], how="diagonal_relaxed")
                    added = len(df) - len(existing_df)
                    updated = 0
            else:
                # No existing data, just insert new data
                added = len(df)
                updated = 0

            # Delete all existing data and reinsert (simplest for SQLite)
            self.execute(f"DELETE FROM {self._table}")  # noqa: S608
        else:
            # New table
            added = len(df)
            updated = 0

        # Insert data
        columns = df.columns
        placeholders = ",".join(["?"] * len(columns))
        col_names = ",".join(f'"{col}"' for col in columns)

        sql = (
            f'INSERT OR REPLACE INTO "{self._table}" ({col_names}) '  # noqa: S608
            f"VALUES ({placeholders})"
        )

        rows = df.rows()
        self.executemany(sql, rows)
        self.commit()

        # Calculate checksum
        checksum = ""
        if self._db_path.exists():
            checksum = file_md5(self._db_path)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            table=self._table,
            row_count=len(df),
            is_merge=is_merge,
            db_path=str(self._db_path),
            checksum=checksum,
        )

        return WriteResultStore(
            file_path=str(self._db_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    # ============ Read operations ============

    @traced("data.read")
    def read(  # type: ignore[override]
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
        rows = self.fetchall(sql, params)

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

        rows = self.fetchall(sql, [index_instrument_id, asof, index_instrument_id])

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

    # ============ Delete operations ============

    @traced("data.delete")
    def delete(  # type: ignore[override]
        self,
        index_instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        """
        Delete index constituent data.

        Args:
            index_instrument_ids: Filter by index instrument IDs.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Number of deleted records.

        """
        # Build delete conditions with correct column names
        conditions: list[str] = []
        params: list[str | int] = []

        if index_instrument_ids:
            placeholders = ",".join("?" * len(index_instrument_ids))
            conditions.append(f"index_instrument_id IN ({placeholders})")
            params.extend(index_instrument_ids)

        if start_date and end_date:
            conditions.append("effective_date >= ? AND effective_date <= ?")
            params.append(start_date)
            params.append(end_date)
        elif start_date:
            conditions.append("effective_date >= ?")
            params.append(start_date)
        elif end_date:
            conditions.append("effective_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        # Count before deletion
        count_sql = f"SELECT COUNT(*) as count FROM {self._table}{where_clause}"  # noqa: S608
        before_result = self.fetchone(count_sql, params)
        before_count = int(before_result["count"]) if before_result else 0

        # Execute deletion
        delete_sql = f"DELETE FROM {self._table}{where_clause}"  # noqa: S608
        self.execute(delete_sql, params)
        self.commit()

        logger.info(
            "Index constituents deleted",
            event="data_delete_complete",
            table=self._table,
            deleted_count=before_count,
        )

        return before_count

    # ============ Count operations ============

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
