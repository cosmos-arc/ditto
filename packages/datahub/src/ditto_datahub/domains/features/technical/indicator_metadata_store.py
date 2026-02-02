"""
IndicatorMetadataStore for technical indicator metadata management.

技术指标元数据存储，使用 SQLite 管理指标的元数据信息.
"""

from __future__ import annotations

from typing import Literal

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IndicatorMetadataStore:
    """
    Technical indicator metadata storage.

    Manages indicator metadata including code, name, type,
    formula, and parameters for technical indicators.
    """

    # Valid indicator types
    TYPE_TREND = "trend"
    TYPE_MOMENTUM = "momentum"
    TYPE_VOLATILITY = "volatility"
    TYPE_VOLUME = "volume"

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize IndicatorMetadataStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        self._init_table()

    def _init_table(self) -> None:
        """Initialize the technical_indicators table if not exists."""
        self._client.execute("""
            CREATE TABLE IF NOT EXISTS technical_indicators (
                indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                formula TEXT,
                parameters TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        self._client.commit()

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
               ORDER BY code""",
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

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
