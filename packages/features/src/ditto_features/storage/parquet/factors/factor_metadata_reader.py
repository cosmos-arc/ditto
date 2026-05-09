"""
FactorMetadata reader for CQRS pattern.

Provides read-only access to factor metadata.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

import polars as pl
from ditto_platform.foundation import SQLiteClient, logger, traced


class FactorMetadataReader:
    """
    Factor metadata reader.

    Provides read-only access to factor metadata including code, name, class,
    family, and PIT requirements.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize FactorMetadataReader.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    @traced("data.metadata_query")
    def get_by_id(self, factor_id: int) -> pl.DataFrame:
        """
        Query factor metadata by ID.

        Args:
            factor_id: Factor ID.

        Returns:
            DataFrame with factor metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying factor metadata by ID",
            factor_id=factor_id,
        )

        rows = self._client.fetchall(
            """SELECT factor_id, code, name, class, family,
                      description, formula, pit_enabled
               FROM factors
               WHERE factor_id = ?""",
            [factor_id],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def get_by_code(self, code: str) -> pl.DataFrame:
        """
        Query factor metadata by code.

        Args:
            code: Factor code.

        Returns:
            DataFrame with factor metadata, or empty DataFrame if not found.

        """
        logger.debug(
            "Querying factor metadata by code",
            code=code,
        )

        rows = self._client.fetchall(
            """SELECT factor_id, code, name, class, family,
                      description, formula, pit_enabled
               FROM factors
               WHERE code = ?""",
            [code],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def batch_get_by_codes(self, codes: list[str]) -> pl.DataFrame:
        """
        Query multiple factor metadata by codes.

        Args:
            codes: List of factor codes.

        Returns:
            DataFrame with factor metadata for all found codes.

        """
        if not codes:
            return pl.DataFrame()

        logger.debug(
            "Batch querying factor metadata by codes",
            codes_count=len(codes),
        )

        # Build placeholders for IN clause
        placeholders = ",".join(["?" for _ in codes])
        rows = self._client.fetchall(
            f"""SELECT factor_id, code, name, class, family,
                      description, formula, pit_enabled
               FROM factors
               WHERE code IN ({placeholders})
               ORDER BY code""",  # noqa: S608 - safe: uses parameterized placeholders
            codes,
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.metadata_query")
    def list_by_family(self, family: str | None = None) -> pl.DataFrame:
        """
        List factors by family.

        Args:
            family: Family filter (None = all families).

        Returns:
            DataFrame with matching factors.

        """
        logger.debug(
            "Listing factors by family",
            family=family,
        )

        if family:
            rows = self._client.fetchall(
                """SELECT factor_id, code, name, class, family,
                          description, formula, pit_enabled
                   FROM factors
                   WHERE family = ?
                   ORDER BY code""",
                [family],
            )
        else:
            rows = self._client.fetchall(
                """SELECT factor_id, code, name, class, family,
                          description, formula, pit_enabled
                   FROM factors
                   ORDER BY code""",
            )

        return pl.DataFrame(rows) if rows else pl.DataFrame()
