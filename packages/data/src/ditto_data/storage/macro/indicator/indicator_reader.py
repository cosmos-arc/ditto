"""
Indicator reader for CQRS pattern.

Provides read-only access to macro indicator data with PIT support.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.storage.sqlite_client import SQLiteClient


class IndicatorReader:
    """
    Macro indicator data reader with PIT support.

    Provides read-only access to macro indicator values with optional
    knowledge_date for Point-in-Time queries.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize IndicatorReader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

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
