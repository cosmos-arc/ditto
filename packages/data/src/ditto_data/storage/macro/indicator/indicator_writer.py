"""
Indicator writer for CQRS pattern.

Provides write access to macro indicator data with PIT support.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_platform.foundation import SQLiteClient, logger, traced


class IndicatorWriter:
    """
    Macro indicator data writer with PIT support.

    Provides write access to macro indicator values with optional
    knowledge_date for Point-in-Time tracking.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize IndicatorWriter.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

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
