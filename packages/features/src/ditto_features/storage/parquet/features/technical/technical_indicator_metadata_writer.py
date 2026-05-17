"""
TechnicalIndicatorMetadata writer for CQRS pattern.

Provides write access to technical indicator metadata.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Literal

from ditto_platform.foundation import SQLiteClient, logger, traced


class TechnicalIndicatorMetadataWriter:
    """
    Technical indicator metadata writer.

    Provides write access to indicator metadata including code, name, type,
    formula, and parameters for technical indicators.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: SQLiteClient) -> None:
        """
        Initialize TechnicalIndicatorMetadataWriter.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    @traced("data.metadata_write")
    def upsert(
        self,
        code: str,
        name: str,
        indicator_type: Literal["trend", "momentum", "volatility", "volume"],
        description: str,
        formula: str,
        parameters: str,
    ) -> int:
        """
        Register or update indicator metadata.

        Args:
            code: Indicator code (e.g., 'indicator_rsi_14').
            name: Indicator display name.
            indicator_type: Indicator type (trend, momentum, volatility, volume).
            description: Description text.
            formula: Calculation formula.
            parameters: JSON string of parameters.

        Returns:
            indicator_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting indicator metadata",
            code=code,
            name=name,
            indicator_type=indicator_type,
        )

        try:
            # Check if exists
            result = self._client.fetchone(
                """SELECT indicator_id FROM technical_indicators WHERE code = ?""",
                [code],
            )
            if result is None:
                # Insert new
                sql = (
                    "INSERT INTO technical_indicators "
                    "(code, name, type, description, formula, parameters) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                )
                indicator_id = self._client.insert_returning_id(
                    sql,
                    [code, name, indicator_type, description, formula, parameters],
                )
            else:
                # Update existing
                indicator_id = result["indicator_id"]
                self._client.execute(
                    """UPDATE technical_indicators
                    SET name = ?, type = ?, description = ?,
                        formula = ?, parameters = ?
                    WHERE indicator_id = ?""",
                    [
                        name,
                        indicator_type,
                        description,
                        formula,
                        parameters,
                        indicator_id,
                    ],
                )
                self._client.commit()

            logger.info(
                "Indicator metadata upserted successfully",
                indicator_id=indicator_id,
                code=code,
            )
            return indicator_id

        except Exception as e:
            self._client.rollback()
            logger.error("Indicator metadata upsert failed", error=str(e))
            raise
