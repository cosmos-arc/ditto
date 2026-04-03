"""
IndicatorMetadata writer for CQRS pattern.

Provides write access to macro indicator metadata.
Following design document at docs/plans/2026-02-09-data-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced

from ditto_data.models.macro import IndicatorMetadataSpec


class IndicatorMetadataWriter:
    """
    Macro indicator metadata writer.

    Provides write access to macro indicator metadata including code,
    name, category, frequency, and PIT requirements.

    Attributes:
        _client: SQLite client for database operations.

    """

    def __init__(self, client: Any) -> None:
        """
        Initialize IndicatorMetadataWriter.

        Args:
            client: SQLite client for database operations.

        """
        self._client = client

    @traced("data.metadata_write")
    def upsert(self, spec: IndicatorMetadataSpec) -> int:
        """
        Register or update indicator metadata.

        Args:
            spec: Indicator metadata specification.

        Returns:
            indicator_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting indicator metadata",
            code=spec.code,
            name=spec.name,
            category=spec.category,
            frequency=spec.frequency,
            need_pit=spec.need_pit,
        )

        try:
            # Try insert first
            result = self._client.fetchone(
                """SELECT indicator_id FROM macro_indicators WHERE code = ?""",
                [spec.code],
            )
            if result is None:
                # Insert new
                sql = (
                    "INSERT INTO macro_indicators "
                    "(code, name, category, frequency, need_pit, "
                    "source, unit, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                )
                indicator_id = self._client.insert_returning_id(
                    sql,
                    [
                        spec.code,
                        spec.name,
                        spec.category,
                        spec.frequency,
                        spec.need_pit,
                        spec.source,
                        spec.unit,
                        spec.description,
                    ],
                )
            else:
                # Update existing
                indicator_id = result["indicator_id"]
                self._client.execute(
                    """UPDATE macro_indicators
                    SET name = ?, category = ?, frequency = ?, need_pit = ?,
                        source = ?, unit = ?, description = ?
                    WHERE indicator_id = ?""",
                    [
                        spec.name,
                        spec.category,
                        spec.frequency,
                        spec.need_pit,
                        spec.source,
                        spec.unit,
                        spec.description,
                        indicator_id,
                    ],
                )
                self._client.commit()

            logger.info(
                "Indicator metadata upserted successfully",
                indicator_id=indicator_id,
                code=spec.code,
            )
            return indicator_id

        except Exception as e:
            self._client.rollback()
            logger.error("Indicator metadata upsert failed", error=str(e))
            raise
