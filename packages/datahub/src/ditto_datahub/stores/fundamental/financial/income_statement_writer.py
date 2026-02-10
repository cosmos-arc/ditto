"""
IncomeStatement writer for CQRS pattern.

Provides write access to income statement data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IncomeStatementWriter:
    """
    Income statement data writer.

    Provides write access to income statement data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize IncomeStatementWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.income_statement_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write income statement data to database.

        Args:
            df: DataFrame with income statement data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting income statement data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO income_statement
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 revenue, operating_profit, net_profit, eps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["revenue"],
                        r["operating_profit"],
                        r["net_profit"],
                        r["eps"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Income statement data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "income_statement", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Income statement write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "income_statement", "status": "failed"}
            )
            raise
