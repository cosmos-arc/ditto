"""IndicatorStore for macro indicator data storage with PIT support."""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IndicatorStore:
    """
    Macro indicator data storage with PIT support.

    Stores macro indicator values with optional knowledge_date for
    Point-in-Time queries.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize IndicatorStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the macro_indicator_data table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS macro_indicator_data (
                indicator_id INTEGER NOT NULL,
                date DATE NOT NULL,
                value REAL NOT NULL,
                knowledge_date DATE,
                effective_from DATE NOT NULL,
                effective_to DATE,
                PRIMARY KEY (indicator_id, date, effective_from)
            )
        """)
        # 创建索引优化 PIT 查询
        self._client.execute("""
            CREATE INDEX IF NOT EXISTS idx_indicator_pit
            ON macro_indicator_data(indicator_id, effective_from, effective_to)
        """)
        self._client.commit()

    def _get_effective_from(self, row: dict[str, Any]) -> date:
        """
        Get effective_from date for a record.

        Uses knowledge_date if available, otherwise uses date.
        This ensures data becomes visible when it's known.

        Args:
            row: Data row dict.

        Returns:
            effective_from date.

        """
        knowledge_date = row.get("knowledge_date")
        if knowledge_date is not None:
            return knowledge_date
        return row["date"]

    @traced("data.indicator_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write macro indicator data to database.

        Args:
            df: DataFrame with columns:
                - indicator_id (int)
                - date (date)
                - value (float)
                - knowledge_date (date, optional)

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting macro indicator data write", record_count=len(df))

        try:
            records = df.to_dicts()
            processed_records: list[list[Any] | tuple[Any, ...]] = []

            for r in records:
                effective_from = self._get_effective_from(r)
                processed_records.append(
                    (
                        r["indicator_id"],
                        r["date"],
                        r["value"],
                        r.get("knowledge_date"),
                        effective_from,
                        None,  # effective_to
                    )
                )

            self._client.executemany(
                """INSERT INTO macro_indicator_data
                (indicator_id, date, value, knowledge_date,
                 effective_from, effective_to)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                processed_records,
            )
            self._client.commit()

            logger.info(
                "Macro indicator data written successfully",
                record_count=len(records),
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Macro indicator write failed", error=str(e))
            raise

    @traced("data.indicator_query")
    def get(
        self,
        indicator_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        as_of_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Query macro indicator data (PIT-safe).

        Args:
            indicator_ids: Filter by indicator IDs (None = all).
            start_date: Start date filter (YYYY-MM-DD).
            end_date: End date filter (YYYY-MM-DD).
            as_of_date: PIT query date - only return data known as of this date.

        Returns:
            DataFrame with indicator data.

        """
        logger.debug(
            "Querying macro indicator data",
            indicator_ids=indicator_ids,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        # Build query conditions
        conditions: list[str] = []
        params: list[str | int] = []

        if indicator_ids:
            placeholders = ",".join("?" * len(indicator_ids))
            conditions.append(f"indicator_id IN ({placeholders})")
            params.extend(indicator_ids)

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)

        # Build WHERE clause
        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        # For PIT queries, use subquery to get the latest version
        if as_of_date:
            # Use window function to get the latest version known as of as_of_date
            sql = f"""
                SELECT indicator_id, date, value, knowledge_date
                FROM (
                    SELECT
                        indicator_id, date, value, knowledge_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY indicator_id, date
                            ORDER BY effective_from DESC
                        ) as rn
                    FROM macro_indicator_data
                    WHERE effective_from <= ?
                      AND (effective_to IS NULL OR effective_to > ?)
                      {where_clause.replace("WHERE ", "AND ")}
                ) ranked
                WHERE rn = 1
                ORDER BY indicator_id, date
            """  # noqa: S608 - where_clause 由白名单条件构建
            params = [as_of_date, as_of_date, *params]
        else:
            # Non-PIT query: return all records
            sql = f"""SELECT indicator_id, date, value, knowledge_date
                     FROM macro_indicator_data
                     {where_clause}
                     ORDER BY indicator_id, date"""  # noqa: S608 - where_clause 由白名单条件构建

        rows = self._client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        # Convert to DataFrame and parse date strings
        df = pl.DataFrame(rows)
        if "date" in df.columns and df["date"].dtype == pl.Utf8:
            df = df.with_columns(pl.col("date").str.strptime(pl.Date, "%Y-%m-%d"))
        if "knowledge_date" in df.columns and df["knowledge_date"].dtype == pl.Utf8:
            df = df.with_columns(
                pl.col("knowledge_date").str.strptime(pl.Date, "%Y-%m-%d")
            )

        return df

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
