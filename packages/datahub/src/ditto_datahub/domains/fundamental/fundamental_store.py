"""FundamentalStore for fundamental data with PIT support."""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class FundamentalStore:
    """
    Fundamental domain data storage with PIT support.

    Core functionality:
    - Financial statements (balance sheet, income statement, cash flow)
    - Corporate actions (dividend, corporate actions)
    - Performance forecast (forecast, express)

    All PIT-enabled datasets support querying data as of a specific date.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
    ) -> None:
        """
        Initialize FundamentalStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()

    # ============================================================================
    # 1. 财务报表数据 (PIT)
    # ============================================================================

    @traced("data.fundamental_write")
    def write_balance_sheet(self, df: pl.DataFrame) -> int:
        """
        Write balance sheet data to database.

        Args:
            df: DataFrame with balance sheet data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting balance sheet data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO balance_sheet
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 total_assets, total_liabilities, net_assets,
                 current_assets, current_liabilities)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["total_assets"],
                        r["total_liabilities"],
                        r["net_assets"],
                        r["current_assets"],
                        r["current_liabilities"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Balance sheet data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "balance_sheet", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Balance sheet write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "balance_sheet", "status": "failed"}
            )
            raise

    @traced("data.fundamental_query")
    def get_balance_sheet(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query balance sheet data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with balance sheet data valid as of as_of_date.

        """
        logger.debug(
            "Querying balance sheet with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      total_assets, total_liabilities, net_assets,
                      current_assets, current_liabilities
               FROM balance_sheet
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.fundamental_write")
    def write_income_statement(self, df: pl.DataFrame) -> int:
        """
        Write income statement data to database.

        Args:
            df: DataFrame with income statement data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting income statement data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO income_statement
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 revenue, operating_profit, net_profit, eps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["revenue"],
                        r["operating_profit"],
                        r["net_profit"],
                        r["eps"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Income statement data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "income_statement", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Income statement write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "income_statement", "status": "failed"}
            )
            raise

    @traced("data.fundamental_query")
    def get_income_statement(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query income statement data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with income statement data valid as of as_of_date.

        """
        logger.debug(
            "Querying income statement with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      revenue, operating_profit, net_profit, eps
               FROM income_statement
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.fundamental_write")
    def write_cash_flow(self, df: pl.DataFrame) -> int:
        """
        Write cash flow data to database.

        Args:
            df: DataFrame with cash flow data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting cash flow data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO cash_flow
                (instrument_id, report_date, knowledge_date,
                 effective_from, effective_to,
                 operating_cash_flow, investing_cash_flow,
                 financing_cash_flow, net_cash_flow)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["report_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["operating_cash_flow"],
                        r["investing_cash_flow"],
                        r["financing_cash_flow"],
                        r["net_cash_flow"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Cash flow data written successfully", record_count=len(records)
            )
            M.data_records.add(
                len(records), {"dataset": "cash_flow", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Cash flow write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "cash_flow", "status": "failed"})
            raise

    @traced("data.fundamental_query")
    def get_cash_flow(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query cash flow data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with cash flow data valid as of as_of_date.

        """
        logger.debug(
            "Querying cash flow with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, report_date, knowledge_date,
                      effective_from, effective_to,
                      operating_cash_flow, investing_cash_flow,
                      financing_cash_flow, net_cash_flow
               FROM cash_flow
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY report_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    # ============================================================================
    # 2. 公司行为数据 (PIT)
    # ============================================================================

    @traced("data.fundamental_write")
    def write_dividend(self, df: pl.DataFrame) -> int:
        """
        Write dividend data to database.

        Args:
            df: DataFrame with dividend data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting dividend data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO dividend
                (instrument_id, ex_dividend_date, knowledge_date,
                 effective_from, effective_to,
                 dividend_per_share, dividend_yield)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["ex_dividend_date"],
                        r["knowledge_date"],
                        r["effective_from"],
                        r.get("effective_to"),
                        r["dividend_per_share"],
                        r["dividend_yield"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info("Dividend data written successfully", record_count=len(records))
            M.data_records.add(
                len(records), {"dataset": "dividend", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Dividend write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "dividend", "status": "failed"})
            raise

    @traced("data.fundamental_query")
    def get_dividend(
        self,
        instrument_id: str,
        as_of_date: date,
    ) -> pl.DataFrame:
        """
        Query dividend data as of a specific date (PIT query).

        Args:
            instrument_id: Instrument identifier.
            as_of_date: Point-in-time query date.

        Returns:
            DataFrame with dividend data valid as of as_of_date.

        """
        logger.debug(
            "Querying dividend with PIT",
            instrument_id=instrument_id,
            as_of_date=as_of_date,
        )

        rows = self._client.fetchall(
            """SELECT instrument_id, ex_dividend_date, knowledge_date,
                      effective_from, effective_to,
                      dividend_per_share, dividend_yield
               FROM dividend
               WHERE instrument_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY ex_dividend_date DESC""",
            [instrument_id, as_of_date, as_of_date],
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()

    @traced("data.fundamental_write")
    def write_corporate_actions(self, df: pl.DataFrame) -> int:
        """
        Write corporate actions data to database (non-PIT).

        Args:
            df: DataFrame with corporate actions data (no PIT columns).

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info("Starting corporate actions data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                """INSERT INTO corporate_actions
                (instrument_id, action_type, announcement_date,
                 effective_date, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["instrument_id"],
                        r["action_type"],
                        r["announcement_date"],
                        r["effective_date"],
                        r["description"],
                    )
                    for r in records
                ],
            )
            self._client.commit()

            logger.info(
                "Corporate actions data written successfully",
                record_count=len(records),
            )
            M.data_records.add(
                len(records), {"dataset": "corporate_actions", "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("Corporate actions write failed", error=str(e))
            M.data_records.add(
                len(df), {"dataset": "corporate_actions", "status": "failed"}
            )
            raise

    @traced("data.fundamental_query")
    def get_corporate_actions(
        self,
        instrument_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pl.DataFrame:
        """
        Query corporate actions data (non-PIT query).

        Args:
            instrument_id: Instrument identifier.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            DataFrame with corporate actions data.

        """
        logger.debug(
            "Querying corporate actions",
            instrument_id=instrument_id,
            start_date=start_date,
            end_date=end_date,
        )

        conditions = ["instrument_id = ?"]
        params: list[Any] = [instrument_id]

        if start_date:
            conditions.append("announcement_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("announcement_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}"

        rows = self._client.fetchall(
            f"""SELECT instrument_id, action_type, announcement_date,
                       effective_date, description
                FROM corporate_actions
                {where_clause}
                ORDER BY announcement_date DESC""",  # noqa: S608
            params,
        )

        return pl.DataFrame(rows) if rows else pl.DataFrame()
