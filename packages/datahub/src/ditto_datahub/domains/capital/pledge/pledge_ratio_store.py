"""PledgeRatioStore for pledge ratio data with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class PledgeRatioStore:
    """
    Pledge ratio data storage with PIT support.

    Stores equity pledge (股权质押) data including pledge ratio and shares.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize PledgeRatioStore."""
        self._client = sqlite_client

    @traced("data.pledge_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write pledge ratio data to database.

        Args:
            df: DataFrame with pledge ratio data including PIT columns.

        Returns:
            Number of records written.

        """
        logger.info("Starting pledge ratio data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO pledge_ratio
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 pledge_ratio, pledge_shares, total_shares)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("pledge_ratio"),
                        r.get("pledge_shares"),
                        r.get("total_shares"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Pledge ratio data written successfully", record_count=len(records)
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Pledge ratio write failed", error=str(e))
            raise

    @traced("data.pledge_query")
    def get(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query pledge ratio data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with pledge ratio data valid as of as_of_date.

        """
        logger.debug(
            "Querying pledge ratio with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      pledge_ratio, pledge_shares, total_shares
               FROM pledge_ratio
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
