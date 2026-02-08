"""IndicatorMetadataStore for macro indicator metadata management."""

from __future__ import annotations

from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IndicatorMetadataStore:
    """
    Macro indicator metadata storage.

    Manages indicator metadata including code, name, category,
    frequency, and PIT requirements.
    """

    # Valid categories
    CATEGORY_ECONOMIC = "economic"
    CATEGORY_INTEREST_RATE = "interest_rate"
    CATEGORY_EXCHANGE_RATE = "exchange_rate"
    CATEGORY_MONEY_SUPPLY = "money_supply"

    # Valid frequencies
    FREQUENCY_DAILY = "daily"
    FREQUENCY_MONTHLY = "monthly"
    FREQUENCY_QUARTERLY = "quarterly"

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize IndicatorMetadataStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the macro_indicators table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS macro_indicators (
                indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                frequency TEXT NOT NULL,
                need_pit BOOLEAN NOT NULL,
                source TEXT,
                unit TEXT,
                description TEXT
            )
        """)
        self._client.commit()

    @traced("data.metadata_write")
    def upsert(  # noqa: PLR0913
        self,
        code: str,
        name: str,
        category: Literal["economic", "interest_rate", "exchange_rate", "money_supply"],
        frequency: Literal["daily", "monthly", "quarterly"],
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

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
