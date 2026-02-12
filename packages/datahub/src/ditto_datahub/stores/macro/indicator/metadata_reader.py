"""
IndicatorMetadata reader for CQRS pattern.

Provides read-only access to macro indicator metadata.
Following design document at docs/plans/2026-02-09-datahub-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import logger, traced


class IndicatorMetadataReader:
    """
    Macro indicator metadata reader.

    Provides read-only access to macro indicator metadata including code,
    name, category, frequency, and PIT requirements.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: Any) -> None:
        """
        Initialize IndicatorMetadataReader.

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
            """SELECT indicator_id, code, name, category, frequency, need_pit,
                      source, unit, description
               FROM macro_indicators
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
            """SELECT indicator_id, code, name, category, frequency, need_pit,
                      source, unit, description
               FROM macro_indicators
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
            f"""SELECT indicator_id, code, name, category, frequency, need_pit,
                      source, unit, description
               FROM macro_indicators
               WHERE code IN ({placeholders})
               ORDER BY code""",  # noqa: S608 - safe: uses parameterized placeholders
            codes,
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def list_by_category(self, category: str | None = None) -> pl.DataFrame:
        """
        List indicators by category.

        Args:
            category: Category filter (None = all categories).

        Returns:
            DataFrame with matching indicators.

        """
        logger.debug(
            "Listing indicators by category",
            category=category,
        )

        if category:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, category, frequency, need_pit,
                          source, unit, description
                   FROM macro_indicators
                   WHERE category = ?
                   ORDER BY code""",
                [category],
            )
        else:
            rows = self._client.fetchall(
                """SELECT indicator_id, code, name, category, frequency, need_pit,
                          source, unit, description
                   FROM macro_indicators
                   ORDER BY code""",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def is_pit_indicator(self, indicator_id: int) -> bool:
        """
        Check if indicator requires PIT tracking.

        Args:
            indicator_id: Indicator ID.

        Returns:
            True if indicator needs PIT, False otherwise.

        """
        row = self._client.fetchone(
            "SELECT need_pit FROM macro_indicators WHERE indicator_id = ?",
            [indicator_id],
        )

        if row is None:
            return False

        return bool(row["need_pit"])

    def get_frequency(self, indicator_id: int) -> str:
        """
        Get indicator frequency.

        Args:
            indicator_id: Indicator ID.

        Returns:
            Frequency string (daily, monthly, quarterly).

        """
        row = self._client.fetchone(
            "SELECT frequency FROM macro_indicators WHERE indicator_id = ?",
            [indicator_id],
        )

        if row is None:
            return "daily"  # Default

        return str(row["frequency"])
