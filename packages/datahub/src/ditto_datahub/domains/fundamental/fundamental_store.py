"""FundamentalStore for fundamental data with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FundamentalStore:
    """
    Fundamental domain data storage with PIT support.

    Core functionality:
    - Financial statements (balance sheet, income statement, cash flow)
    - Corporate actions (dividend, corporate actions)
    - Performance forecast (forecast, express)

    All PIT-enabled datasets support querying data as of a specific date.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """
        Initialize FundamentalStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()

    # ============================================================================
    # 1. 财务报表数据 (PIT)
    # ============================================================================

    @traced("data.fundamental_write")
    def write_balance_sheet(self, df: pl.DataFrame) -> int:
        """
        Write balance sheet data to database.

        Args:
            df: DataFrame with balance sheet data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

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
            M.data_records.add(
                len(records), {"dataset": "balance_sheet", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Balance sheet write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "balance_sheet", "status": "failed"}
            )
            raise

    @traced("data.fundamental_query")
    def get_balance_sheet(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query balance sheet data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with balance sheet data valid as of as_of_date.

        """
        logger.debug(
            "Querying balance sheet with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      total_assets, total_liabilities, net_assets,
                      current_assets, current_liabilities
               FROM balance_sheet
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()
