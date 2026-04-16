"""
CorporateActions reader for CQRS pattern.

Provides read-only access to corporate actions data with PIT support.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_infra.foundation import logger, traced

from ditto_data.storage.sqlite_client import SQLiteClient


class CorporateActionsReader:
    """
    Corporate actions data reader.

    Provides read-only access to corporate actions data with date range
    filtering and optional PIT (Point-in-Time) support.

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
        instrument_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """
        Query corporate actions data with optional date range and PIT filtering.

        Args:
            instrument_id: Instrument identifier.
            start_date: Optional start date filter (inclusive) on action_date.
            end_date: Optional end date filter (inclusive) on action_date.
            as_of_date: Optional PIT query date. When provided, only versions
                effective at that date are returned
                (effective_from <= as_of_date AND
                 effective_to IS NULL OR effective_to > as_of_date).

        Returns:
            DataFrame with corporate actions data. Returns empty DataFrame
            if no data found.

        """
        logger.debug(
            "Querying corporate actions",
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )

        conditions = ["instrument_id = ?"]
        params: list[Any] = [instrument_id]

        if start_date:
            conditions.append("action_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("action_date <= ?")
            params.append(end_date)

        if as_of_date is not None:
            conditions.append("effective_from <= ?")
            params.append(as_of_date)
            conditions.append("(effective_to IS NULL OR effective_to > ?)")
            params.append(as_of_date)

        where_clause = f" WHERE {' AND '.join(conditions)}"

        rows = self._client.fetchall(
            f"""SELECT instrument_id, action_type, action_date,
                       knowledge_date, effective_from, effective_to, description
                FROM corporate_actions
                {where_clause}
                ORDER BY action_date DESC""",  # noqa: S608 - where_clause constructed from whitelisted conditions
            params,
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
