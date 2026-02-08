"""ExpressStore for performance express data with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class ExpressStore:
    """
    Performance express data storage with PIT support.

    Stores company performance express/announcement data.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize ExpressStore."""
        self._client = sqlite_client

    @traced("data.express_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write express data to database.

        Args:
            df: DataFrame with express data including PIT columns.

        Returns:
            Number of records written.

        """
        logger.info("Starting express data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO express
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to, type,
                 profit_range_min, profit_range_max)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["type"],
                        r.get("profit_range_min"),
                        r.get("profit_range_max"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Express data written successfully", record_count=len(records))
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Express write failed", error=str(e))
            raise

    @traced("data.express_query")
    def get(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query express data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with express data valid as of as_of_date.

        """
        logger.debug(
            "Querying express with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to, type,
                      profit_range_min, profit_range_max
               FROM express
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
