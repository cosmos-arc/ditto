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
            records = sorted(
                df.to_dicts(),
                key=lambda row: (
                    row["indicator_id"],
                    row["date"],
                    self._get_effective_from(row),
                ),
            )
            written = 0

            for row in records:
                written += self._write_revision(row)

            self._client.commit()

            logger.info(
                "Macro indicator data written successfully",
                record_count=written,
                attempted_count=len(records),
            )
            return written

        except Exception as e:
            self._client.rollback()
            logger.error("Macro indicator write failed", error=str(e))
            raise

    def _write_revision(self, row: dict[str, Any]) -> int:
        """Write one value change while maintaining left-closed PIT intervals."""
        indicator_id = row["indicator_id"]
        observation_date = row["date"]
        value = row["value"]
        knowledge_date = row.get("knowledge_date")
        effective_from = self._get_effective_from(row)
        identity = [indicator_id, observation_date]

        exact = self._client.fetchone(
            """SELECT value FROM macro_indicator_data
            WHERE indicator_id = ? AND date = ? AND effective_from = ?""",
            [*identity, effective_from],
        )
        if exact is not None:
            if exact["value"] == value:
                return 0
            cursor = self._client.execute(
                """UPDATE macro_indicator_data
                SET value = ?, knowledge_date = ?
                WHERE indicator_id = ? AND date = ? AND effective_from = ?""",
                [value, knowledge_date, *identity, effective_from],
            )
            return cursor.rowcount

        predecessor = self._client.fetchone(
            """SELECT value, effective_from FROM macro_indicator_data
            WHERE indicator_id = ? AND date = ? AND effective_from < ?
            ORDER BY effective_from DESC LIMIT 1""",
            [*identity, effective_from],
        )
        if predecessor is not None and predecessor["value"] == value:
            # Tushare China macro endpoints expose retrieval snapshots rather
            # than provider vintages. A later retrieval date with an unchanged
            # value must not manufacture a revision.
            return 0

        successor = self._client.fetchone(
            """SELECT effective_from FROM macro_indicator_data
            WHERE indicator_id = ? AND date = ? AND effective_from > ?
            ORDER BY effective_from ASC LIMIT 1""",
            [*identity, effective_from],
        )
        effective_to = successor["effective_from"] if successor is not None else None
        self._client.execute(
            """INSERT INTO macro_indicator_data
            (indicator_id, date, value, knowledge_date, effective_from, effective_to)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [
                indicator_id,
                observation_date,
                value,
                knowledge_date,
                effective_from,
                effective_to,
            ],
        )
        if predecessor is not None:
            self._client.execute(
                """UPDATE macro_indicator_data SET effective_to = ?
                WHERE indicator_id = ? AND date = ? AND effective_from = ?""",
                [
                    effective_from,
                    indicator_id,
                    observation_date,
                    predecessor["effective_from"],
                ],
            )
        return 1
