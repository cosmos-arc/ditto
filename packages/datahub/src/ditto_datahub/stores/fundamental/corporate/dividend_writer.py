"""
Dividend writer for CQRS pattern.

Provides write access to dividend data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class DividendWriter:
    """
    Dividend data writer.

    Provides write access to dividend data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize DividendWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.dividend_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write dividend data to database.

        Args:
            df: DataFrame with dividend data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting dividend data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO dividend
                (instrument_id, ex_dividend_date, knowledge_date,
                 effective_from, effective_to,
                 dividend_per_share, dividend_yield)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["ex_dividend_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["dividend_per_share"],
                        r["dividend_yield"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Dividend data written successfully", record_count=len(records))
            M.data_records.add(
                len(records), {"dataset": "dividend", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Dividend write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "dividend", "status": "failed"})
            raise
