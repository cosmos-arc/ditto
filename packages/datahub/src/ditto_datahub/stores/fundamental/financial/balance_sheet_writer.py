"""
BalanceSheet writer for CQRS pattern.

Provides write access to balance sheet data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import Metrics, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class BalanceSheetWriter:
    """
    Balance sheet data writer.

    Provides write access to balance sheet data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize BalanceSheetWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.balance_sheet_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write balance sheet data to database.

        Args:
            df: DataFrame with balance sheet data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting balance sheet data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO balance_sheet
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 total_assets, total_liabilities, net_assets,
                 current_assets, current_liabilities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["total_assets"],
                        r["total_liabilities"],
                        r["net_assets"],
                        r["current_assets"],
                        r["current_liabilities"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Balance sheet data written successfully", record_count=len(records)
            )
            Metrics.data_records.add(
                len(records), {"dataset": "balance_sheet", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Balance sheet write failed", error=str(e))
            Metrics.data_records.add(
                len(df), {"dataset": "balance_sheet", "status": "failed"}
            )
            raise
