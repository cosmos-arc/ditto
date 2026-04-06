"""
TechnicalIndicatorMetadata reader for CQRS pattern.

Provides read-only access to technical indicator metadata.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_infra.foundation import logger, traced


class TechnicalIndicatorMetadataReader:
    """
    Technical indicator metadata reader.

    Provides read-only access to indicator metadata including code, name, type,
    formula, and parameters for technical indicators.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: Any) -> None:
        """
        Initialize TechnicalIndicatorMetadataReader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    @traced("data.metadata_query")
    def get_by_id(self, indicator_id: int) -> pl.DataFrame:
        """
        Query indicator metadata by ID.

        Args:
            indicator_id: Indicator ID.

        Returns:
            DataFrame with indicator metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying indicator metadata by ID",
            indicator_id=indicator_id,
        )

        rows = self._client.fetchall(
            """SELECT indicator_id, code, name, type, description, formula, parameters
               FROM technical_indicators
               WHERE indicator_id = ?""",
            [indicator_id],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def get_by_code(self, code: str) -> pl.DataFrame:
        """
        Query indicator metadata by code.

        Args:
            code: Indicator code.

        Returns:
            DataFrame with indicator metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying indicator metadata by code",
            code=code,
        )

        rows = self._client.fetchall(
            """SELECT indicator_id, code, name, type, description, formula, parameters
               FROM technical_indicators
               WHERE code = ?""",
            [code],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def batch_get_by_codes(self, codes: list[str]) -> pl.DataFrame:
        """
        Query multiple indicator metadata by codes.

        Args:
            codes: List of indicator codes.

        Returns:
            DataFrame with indicator metadata for all found codes.

        """
        if not codes:
            return pl.DataFrame()

        logger.debug(
            "Batch querying indicator metadata by codes",
            codes_count=len(codes),
        )

        # Build placeholders for IN clause
        placeholders = ",".join(["?" for _ in codes])
        rows = self._client.fetchall(
            f"""SELECT indicator_id, code, name, type, description, formula, parameters
               FROM technical_indicators
               WHERE code IN ({placeholders})
               ORDER BY code""",  # noqa: S608 - codes 使用参数化占位符
            codes,
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def list_by_type(self, indicator_type: str | None = None) -> pl.DataFrame:
        """
        List indicators by type.

        Args:
            indicator_type: Type filter (None = all types).

        Returns:
            DataFrame with matching indicators.

        """
        logger.debug(
            "Listing indicators by type",
            indicator_type=indicator_type,
        )

        if indicator_type:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, type,
                   description, formula, parameters
                   FROM technical_indicators
                   WHERE type = ?
                   ORDER BY code""",
                [indicator_type],
            )
        else:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, type,
                   description, formula, parameters
                   FROM technical_indicators
                   ORDER BY code""",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()
