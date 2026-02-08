"""CapitalStore - Capital domain data storage with PIT support."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.capital.margin.margin_trading_store import MarginTradingStore
from ditto_datahub.stores.capital.pledge.pledge_ratio_store import PledgeRatioStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


class CapitalStore:
    """
    Capital domain data storage with PIT support.

    Provides complete CRUD operations including write and query methods.
    Service layer provides thin wrapper with dependency injection.

    Core functionality:
    - Margin trading (融资融券)
    - Pledge ratio (股权质押)
    - Valuation metrics (估值指标)
    - Futures (期货)
    - Index composition (指数成分股)

    Delegates to sub-domain stores for margin and pledge data.
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """Initialize CapitalStore."""
        self._client = sqlite_client
        self._margin_store = MarginTradingStore(sqlite_client)
        self._pledge_store = PledgeRatioStore(sqlite_client)

    # ============ Margin trading (delegation) ============

    @traced("data.capital_write")
    def write_margin_trading(self, df: pl.DataFrame) -> int:
        """Write margin trading data."""
        return self._margin_store.write(df)

    # ============ Pledge ratio (delegation) ============

    @traced("data.capital_write")
    def write_pledge_ratio(self, df: pl.DataFrame) -> int:
        """Write pledge ratio data."""
        return self._pledge_store.write(df)

    # ============ Valuation metrics (direct implementation) ============

    @traced("data.capital_write")
    def write_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Write valuation metrics data.

        Args:
            df: DataFrame with valuation metrics data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting valuation metrics data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO valuation_metrics
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("pe_ratio"),
                        r.get("pb_ratio"),
                        r.get("ps_ratio"),
                        r.get("dividend_yield"),
                        r.get("market_cap"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Valuation metrics data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "valuation_metrics", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Valuation metrics write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "valuation_metrics", "status": "failed"}
            )
            raise

    # ============ Futures (direct implementation) ============

    @traced("data.capital_write")
    def write_futures(self, df: pl.DataFrame) -> int:
        """
        Write futures data.

        Args:
            df: DataFrame with futures data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting futures data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO futures
                (instrument_id, trade_date, knowledge_date,
                 effective_from, effective_to,
                 open_interest, settlement_price, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["trade_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r.get("open_interest"),
                        r.get("settlement_price"),
                        r.get("volume"),
                        r.get("turnover"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Futures data written successfully", record_count=len(records))
            M.data_records.add(
                len(records), {"dataset": "futures", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Futures write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "futures", "status": "failed"})
            raise

    # ============ Index composition (direct implementation) ============

    @traced("data.capital_write")
    def write_index_composition(self, df: pl.DataFrame) -> int:
        """
        Write index composition data.

        Args:
            df: DataFrame with index composition data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting index composition data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO index_composition
                (index_id, instrument_id, weight, effective_from, effective_to)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["index_id"],
                        r["instrument_id"],
                        r.get("weight"),
                        r["effective_from"],
                        r.get("effective_to"),
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Index composition data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "index_composition", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Index composition write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "index_composition", "status": "failed"}
            )
            raise

    # ============ Query methods (PIT) ============

    @traced("data.capital_query")
    def get_margin_trading(
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
        return self._margin_store.get(instrument_id, as_of_date)

    @traced("data.capital_query")
    def get_pledge_ratio(
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
        return self._pledge_store.get(instrument_id, as_of_date)

    @traced("data.capital_query")
    def get_valuation_metrics(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query valuation metrics data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with valuation metrics data valid as of as_of_date.

        """
        logger.debug(
            "Querying valuation metrics with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, trade_date, knowledge_date,
                      effective_from, effective_to,
                      pe_ratio, pb_ratio, ps_ratio, dividend_yield, market_cap
               FROM valuation_metrics
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY trade_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.capital_query")
    def get_futures(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query futures data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with futures data valid as of as_of_date.

        """
        logger.debug(
            "Querying futures with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, trade_date, knowledge_date,
                      effective_from, effective_to,
                      open_interest, settlement_price, volume, turnover
               FROM futures
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY trade_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.capital_query")
    def get_index_composition(
        self,
        index_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query index composition data as of a specific date (PIT query).

        Args:
            index_id: Index identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with index composition data valid as of as_of_date.

        """
        logger.debug(
            "Querying index composition with PIT",
            index_id=index_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT index_id, instrument_id, weight, effective_from, effective_to
               FROM index_composition
               WHERE index_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY instrument_id""",
            [index_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._margin_store.close()
        self._pledge_store.close()
        self._client.close()
