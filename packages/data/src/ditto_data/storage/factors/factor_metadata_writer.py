"""
FactorMetadata writer for CQRS pattern.

Provides write access to factor metadata.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Literal

from ditto_infra.foundation import logger, traced

from ditto_data.storage.sqlite_client import SQLiteClient


class FactorMetadataWriter:
    """
    Factor metadata writer.

    Provides write access to factor metadata including code, name, class,
    family, and PIT requirements.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize FactorMetadataWriter.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

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
