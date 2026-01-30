"""MarginTradingStore for margin trading data with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class MarginTradingStore:
    """
    Margin trading data storage with PIT support.

    Stores margin trading (融资融券) data including buy/sell balances and volumes.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize MarginTradingStore."""
        self._client = sqlite_client

    @traced("data.margin_write")
    def write(self, df: pl.DataFrame) -> int:
        """
        Write margin trading data to database.

        Args:
            df: DataFrame with margin trading data including PIT columns.

        Returns:
            Number of records written.

        """
        logger.info("Starting margin trading data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO margin_trading
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 margin_buy_balance, short_sell_balance,
                 margin_buy_volume, short_sell_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("margin_buy_balance"),
                        r.get("short_sell_balance"),
                        r.get("margin_buy_volume"),
                        r.get("short_sell_volume"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Margin trading data written successfully", record_count=len(records)
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Margin trading write failed", error=str(e))
            raise

    @traced("data.margin_query")
    def get(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query margin trading data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with margin trading data valid as of as_of_date.

        """
        logger.debug(
            "Querying margin trading with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, trade_date, knowledge_date,
                      effective_from, effective_to,
                      margin_buy_balance, short_sell_balance,
                      margin_buy_volume, short_sell_volume
               FROM margin_trading
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY trade_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
