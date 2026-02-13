"""
Express writer for CQRS pattern.

Provides write access to express data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class ExpressWriter:
    """
    Express data writer.

    Provides write access to express data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize ExpressWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.express_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write express data to database.

        Args:
            df: DataFrame with express data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting express data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO express
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to, type,
                 profit_range_min, profit_range_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["type"],
                        r.get("profit_range_min"),
                        r.get("profit_range_max"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Express data written successfully", record_count=len(records))
            M.data_records.add(
                len(records), {"dataset": "express", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Express write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "express", "status": "failed"})
            raise
