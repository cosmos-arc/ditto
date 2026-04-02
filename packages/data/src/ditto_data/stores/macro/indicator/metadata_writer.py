"""
IndicatorMetadata writer for CQRS pattern.

Provides write access to macro indicator metadata.
Following design document at docs/plans/2026-02-09-datahub-cqrs-refactor.md
"""

from __future__ import annotations

from typing import Any

from ditto_infra.foundation import logger, traced

from ditto_data.models.macro import MacroCategory, MacroFrequency


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
    def upsert(
        self,
        code: str,
        name: str,
        category: MacroCategory,
        frequency: MacroFrequency,
        need_pit: bool,
        source: str | None = None,
        unit: str | None = None,
        description: str | None = None,
    ) -> int:
        """
        Register or update indicator metadata.

        Args:
            code: Indicator code (e.g., 'CPI_YOY', 'SHIBOR_1M').
            name: Indicator display name.
            category: Category (economic, interest_rate, exchange_rate, money_supply).
            frequency: Data frequency (daily, monthly, quarterly).
            need_pit: Whether this indicator needs PIT tracking.
            source: Data source (e.g., 'tushare', 'akshare').
            unit: Unit of measurement (e.g., '%', '亿元').
            description: Description text.

        Returns:
            indicator_id

        Raises:
            Exception: If database operation fails.

        """
        logger.info(
            "Upserting indicator metadata",
            code=code,
            name=name,
            category=category,
            frequency=frequency,
            need_pit=need_pit,
        )

        try:
            # Try insert first
            result = self._client.fetchone(
                """SELECT indicator_id FROM macro_indicators WHERE code = ?""",
                [code],
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
                        code,
                        name,
                        category,
                        frequency,
                        need_pit,
                        source,
                        unit,
                        description,
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
                        name,
                        category,
                        frequency,
                        need_pit,
                        source,
                        unit,
                        description,
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
