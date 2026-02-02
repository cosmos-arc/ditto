"""FactorMetadataStore for factor metadata management."""

from __future__ import annotations

from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FactorMetadataStore:
    """
    Factor metadata storage.

    Manages factor metadata including code, name, class,
    family, and PIT requirements.
    """

    # Valid factor classes
    CLASS_FUNDAMENTAL = "fundamental"
    CLASS_TECHNICAL = "technical"
    CLASS_MACRO = "macro"
    CLASS_STATISTICAL = "statistical"

    # Valid factor families
    FAMILY_VALUE = "value"
    FAMILY_MOMENTUM = "momentum"
    FAMILY_QUALITY = "quality"
    FAMILY_SIZE = "size"
    FAMILY_VOLATILITY = "volatility"

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize FactorMetadataStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the factors table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS factors (
                factor_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                class TEXT NOT NULL,
                family TEXT NOT NULL,
                description TEXT,
                formula TEXT,
                pit_enabled BOOLEAN NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        self._client.commit()

    @traced("data.metadata_write")
    def upsert(
        self,
        code: str,
        name: str,
        factor_class: Literal["fundamental", "technical", "macro", "statistical"],
        family: Literal["value", "momentum", "quality", "size", "volatility"],
        description: str,
        formula: str,
        pit_enabled: bool,
    ) -> int:
        """
        Register or update factor metadata.

        Args:
            code: Factor code (e.g., 'factor_momentum_12m').
            name: Factor display name.
            factor_class: Factor class (fundamental, technical, macro, statistical).
            family: Factor family (value, momentum, quality, size, volatility).
            description: Description text.
            formula: Calculation formula.
            pit_enabled: Whether PIT tracking is enabled.

        Returns:
            factor_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting factor metadata",
            code=code,
            name=name,
            factor_class=factor_class,
            family=family,
        )

        try:
            # Check if exists
            result = self._client.fetchone(
                """SELECT factor_id FROM factors WHERE code = ?""",
                [code],
            )
            if result is None:
                # Insert new
                sql = (
                    "INSERT INTO factors "
                    "(code, name, class, family, description, formula, pit_enabled) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)"
                )
                factor_id = self._client.insert_returning_id(
                    sql,
                    [
                        code,
                        name,
                        factor_class,
                        family,
                        description,
                        formula,
                        pit_enabled,
                    ],
                )
            else:
                # Update existing
                factor_id = result["factor_id"]
                self._client.execute(
                    """UPDATE factors
                    SET name = ?, class = ?, family = ?, description = ?,
                        formula = ?, pit_enabled = ?
                    WHERE factor_id = ?""",
                    [
                        name,
                        factor_class,
                        family,
                        description,
                        formula,
                        pit_enabled,
                        factor_id,
                    ],
                )
                self._client.commit()

            logger.info(
                "Factor metadata upserted successfully",
                factor_id=factor_id,
                code=code,
            )
            return factor_id

        except Exception as e:
            self._client.rollback()
            logger.error("Factor metadata upsert failed", error=str(e))
            raise

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
               ORDER BY code""",
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

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
