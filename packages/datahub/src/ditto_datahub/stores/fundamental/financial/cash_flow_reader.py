"""
CashFlow reader for CQRS pattern.

Provides read-only access to cash flow data with PIT support.
"""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class CashFlowReader:
    """
    Cash flow data reader.

    Provides read-only access to cash flow data with Point-in-Time
    query support for accurate historical analysis.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize CashFlowReader.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.cash_flow_query")
    def get(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query cash flow data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with cash flow data valid as of as_of_date.
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying cash flow with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      operating_cash_flow, investing_cash_flow,
                      financing_cash_flow, net_cash_flow
               FROM cash_flow
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
