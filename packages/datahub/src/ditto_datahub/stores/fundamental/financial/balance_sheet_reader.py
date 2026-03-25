"""
BalanceSheet reader for CQRS pattern.

Provides read-only access to balance sheet data with PIT support.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class BalanceSheetReader:
    """
    Balance sheet data reader.

    Provides read-only access to balance sheet data with Point-in-Time
    query support for accurate historical analysis.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize BalanceSheetReader.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.balance_sheet_query")
    def get(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query balance sheet data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with balance sheet data valid as of as_of_date.
            Returns empty DataFrame if no data found.

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
