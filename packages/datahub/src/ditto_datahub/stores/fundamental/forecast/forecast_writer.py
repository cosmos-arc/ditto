"""
Forecast writer for CQRS pattern.

Provides write access to forecast data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class ForecastWriter:
    """
    Performance forecast data writer.

    Provides write access to company performance forecast/announcement
    data with transaction support and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize ForecastWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.forecast_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write forecast data to database.

        Args:
            df: DataFrame with forecast data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting forecast data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO forecast
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

            logger.info("Forecast data written successfully", record_count=len(records))
            Metrics.data_records.add(
                len(records), {"dataset": "forecast", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Forecast write failed", error=str(e))
            Metrics.data_records.add(
                len(df), {"dataset": "forecast", "status": "failed"}
            )
            raise
