"""
CorporateActions writer for CQRS pattern.

Provides write access to corporate actions data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_data.stores.sqlite_client import SQLiteClient


class CorporateActionsWriter:
    """
    Corporate actions data writer.

    Provides write access to corporate actions data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize CorporateActionsWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.corporate_actions_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write corporate actions data to database (non-PIT).

        Args:
            df: DataFrame with corporate actions data (no PIT columns).

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting corporate actions data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO corporate_actions
                (instrument_id, action_type, announcement_date,
                 effective_date, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["action_type"],
                        r["announcement_date"],
                        r["effective_date"],
                        r["description"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Corporate actions data written successfully",
                record_count=len(records),
            )
            Metrics.data_records.add(
                len(records), {"dataset": "corporate_actions", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Corporate actions write failed", error=str(e))
            Metrics.data_records.add(
                len(df), {"dataset": "corporate_actions", "status": "failed"}
            )
            raise
