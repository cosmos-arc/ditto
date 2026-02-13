"""
CashFlow writer for CQRS pattern.

Provides write access to cash flow data with error handling.
"""

from __future__ import annotations

import polars as pl
from ditto_infra.foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class CashFlowWriter:
    """
    Cash flow data writer.

    Provides write access to cash flow data with transaction support
    and automatic rollback on error.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize CashFlowWriter.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.cash_flow_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write cash flow data to database.

        Args:
            df: DataFrame with cash flow data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails (transaction rolled back).

        """
        logger.info("Starting cash flow data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO cash_flow
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 operating_cash_flow, investing_cash_flow,
                 financing_cash_flow, net_cash_flow)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["operating_cash_flow"],
                        r["investing_cash_flow"],
                        r["financing_cash_flow"],
                        r["net_cash_flow"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Cash flow data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "cash_flow", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Cash flow write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "cash_flow", "status": "failed"})
            raise
