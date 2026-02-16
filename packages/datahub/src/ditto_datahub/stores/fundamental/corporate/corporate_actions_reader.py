"""
CorporateActions reader for CQRS pattern.

Provides read-only access to corporate actions data (non-PIT).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class CorporateActionsReader:
    """
    Corporate actions data reader.

    Provides read-only access to corporate actions data with date range
    filtering support. This is a non-PIT table without effective_from/effective_to.

    Attributes:
        _client: SQLite client for database access.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize CorporateActionsReader.

        Args:
            client: SQLite client instance.

        """
        self._client = client

    @traced("data.corporate_actions_query")
    def get(
        self,
        instrument_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """
        Query corporate actions data with optional date range filtering.

        Args:
            instrument_id: Instrument identifier.
            start_date: Optional start date filter (inclusive).
            end_date: Optional end date filter (inclusive).

        Returns:
            DataFrame with corporate actions data. Returns empty DataFrame
            if no data found.

        """
        logger.debug(
            "Querying corporate actions",
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
        )

        conditions = ["instrument_id = ?"]
        params: list[Any] = [instrument_id]

        if start_date:
            conditions.append("announcement_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("announcement_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}"

        rows = self._client.fetchall(
            f"""SELECT instrument_id, action_type, announcement_date,
                       effective_date, description
                FROM corporate_actions
                {where_clause}
                ORDER BY announcement_date DESC""",  # noqa: S608 - where_clause constructed from whitelisted conditions
            params,
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
