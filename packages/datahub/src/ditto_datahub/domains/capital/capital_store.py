"""
CapitalStore for capital and financial data with PIT support.

This module provides storage and retrieval for capital domain data
including financial statements, valuation metrics, derivatives, and
index composition with Point-in-Time support.

Core functionality:
- write_balance_sheet / get_balance_sheet: 资产负债表（PIT）
- write_income_statement / get_income_statement: 利润表（PIT）
- write_cash_flow / get_cash_flow: 现金流量表（PIT）

PIT Query Pattern:
  effective_from <= as_of_date AND (effective_to IS NULL OR effective_to > as_of_date)
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced
from ditto_foundation.cache import DataCache

from ditto_datahub.stores.sqlite_client import SQLiteClient


class CapitalStore:
    """
    Capital domain data storage with PIT support.

    Core functionality:
    - Financial statements (balance sheet, income statement, cash flow)
    - Valuation metrics
    - Derivatives data
    - Index composition
    - Corporate actions
    - Dividend, margin trading, pledge ratio

    All PIT-enabled datasets support querying data as of a specific date.

    Note: CapitalStore uses SQLiteClient for data access, similar to
    InstrumentStore. This design maintains consistency with the existing
    architecture while providing PIT capabilities.
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any] | None = None,
    ) -> None:
        """
        Initialize CapitalStore.

        Args:
            sqlite_client: SQLite client for database operations.
            data_cache: Optional DataCache for query result caching.

        """
        self._client = sqlite_client
        self._data_cache = data_cache

    # ============================================================================
    # 1. 财务报表数据 (PIT)
    # ============================================================================

    @traced("data.capital_write")
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
        logger.info(
            "Starting balance sheet data write",
            event="balance_sheet_write_start",
            record_count=len(df),
        )

        try:
            # Convert DataFrame to records for insertion
            records = df.to_dicts()

            # Batch insert using executemany
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
                        r.get("effective_to"),  # Can be None
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
                "Balance sheet data written successfully",
                event="balance_sheet_write_complete",
                record_count=len(records),
            )

            # Record metrics
            M.data_records.add(
                len(records), {"dataset": "balance_sheet", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Balance sheet write failed",
                event="balance_sheet_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "balance_sheet", "status": "failed"}
            )
            raise

    @traced("data.capital_query")
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
            Returns empty DataFrame if no data found.

        Query logic:
            effective_from <= as_of_date AND
            (effective_to IS NULL OR effective_to > as_of_date)

        """
        logger.debug(
            "Querying balance sheet with PIT",
            event="balance_sheet_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        # 尝试从 DataCache 获取
        if self._data_cache:
            cache_key = f"balance_sheet:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

        # 从数据库查询
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

        if not rows:
            logger.debug(
                "No balance sheet data found",
                event="balance_sheet_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        # 缓存结果
        if self._data_cache:
            cache_key = f"balance_sheet:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Balance sheet query completed",
            event="balance_sheet_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    @traced("data.capital_write")
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
        logger.info(
            "Starting income statement data write",
            event="income_statement_write_start",
            record_count=len(df),
        )

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
                "Income statement data written successfully",
                event="income_statement_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "income_statement", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Income statement write failed",
                event="income_statement_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "income_statement", "status": "failed"}
            )
            raise

    @traced("data.capital_query")
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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying income statement with PIT",
            event="income_statement_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"income_statement:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No income statement data found",
                event="income_statement_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"income_statement:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Income statement query completed",
            event="income_statement_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    @traced("data.capital_write")
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
        logger.info(
            "Starting cash flow data write",
            event="cash_flow_write_start",
            record_count=len(df),
        )

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
                "Cash flow data written successfully",
                event="cash_flow_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "cash_flow", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Cash flow write failed",
                event="cash_flow_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(len(df), {"dataset": "cash_flow", "status": "failed"})
            raise

    @traced("data.capital_query")
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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying cash flow with PIT",
            event="cash_flow_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"cash_flow:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No cash flow data found",
                event="cash_flow_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"cash_flow:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Cash flow query completed",
            event="cash_flow_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 2. 估值指标数据 (PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Write valuation metrics data to database.

        Args:
            df: DataFrame with valuation metrics data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting valuation metrics data write",
            event="valuation_metrics_write_start",
            record_count=len(df),
        )

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
                        r["pe_ratio"],
                        r["pb_ratio"],
                        r["ps_ratio"],
                        r["dividend_yield"],
                        r["market_cap"],
                    )
                    for r in records
                ],
            )

            self._client.commit()

            logger.info(
                "Valuation metrics data written successfully",
                event="valuation_metrics_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "valuation_metrics", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Valuation metrics write failed",
                event="valuation_metrics_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "valuation_metrics", "status": "failed"}
            )
            raise

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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying valuation metrics with PIT",
            event="valuation_metrics_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"valuation_metrics:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No valuation metrics data found",
                event="valuation_metrics_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"valuation_metrics:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Valuation metrics query completed",
            event="valuation_metrics_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 3. 衍生品数据 (PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_futures(self, df: pl.DataFrame) -> int:
        """
        Write futures data to database.

        Args:
            df: DataFrame with futures data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting futures data write",
            event="futures_write_start",
            record_count=len(df),
        )

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
                        r["open_interest"],
                        r["settlement_price"],
                        r["volume"],
                        r["turnover"],
                    )
                    for r in records
                ],
            )

            self._client.commit()

            logger.info(
                "Futures data written successfully",
                event="futures_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "futures", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Futures write failed",
                event="futures_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(len(df), {"dataset": "futures", "status": "failed"})
            raise

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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying futures with PIT",
            event="futures_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"futures:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No futures data found",
                event="futures_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"futures:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Futures query completed",
            event="futures_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 4. 成分股数据 (PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_index_composition(self, df: pl.DataFrame) -> int:
        """
        Write index composition data to database.

        Args:
            df: DataFrame with index composition data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting index composition data write",
            event="index_composition_write_start",
            record_count=len(df),
        )

        try:
            records = df.to_dicts()

            self._client.executemany(
                """INSERT INTO index_composition
                (index_id, instrument_id, weight,
                 effective_from, effective_to)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING""",
                [
                    (
                        r["index_id"],
                        r["instrument_id"],
                        r["weight"],
                        r["effective_from"],
                        r.get("effective_to"),
                    )
                    for r in records
                ],
            )

            self._client.commit()

            logger.info(
                "Index composition data written successfully",
                event="index_composition_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "index_composition", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Index composition write failed",
                event="index_composition_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "index_composition", "status": "failed"}
            )
            raise

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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying index composition with PIT",
            event="index_composition_query_start",
            index_id=index_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"index_composition:{index_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

        rows = self._client.fetchall(
            """SELECT index_id, instrument_id, weight,
                      effective_from, effective_to
               FROM index_composition
               WHERE index_id = ?
                 AND effective_from <= ?
                 AND (effective_to IS NULL OR effective_to > ?)
               ORDER BY weight DESC""",
            [index_id, as_of_date, as_of_date],
        )

        if not rows:
            logger.debug(
                "No index composition data found",
                event="index_composition_query_not_found",
                index_id=index_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"index_composition:{index_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Index composition query completed",
            event="index_composition_query_complete",
            index_id=index_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 5. 股息分红 (PIT)
    # ============================================================================

    @traced("data.capital_write")
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
        logger.info(
            "Starting dividend data write",
            event="dividend_write_start",
            record_count=len(df),
        )

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

            logger.info(
                "Dividend data written successfully",
                event="dividend_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "dividend", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Dividend write failed",
                event="dividend_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(len(df), {"dataset": "dividend", "status": "failed"})
            raise

    @traced("data.capital_query")
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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying dividend with PIT",
            event="dividend_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"dividend:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No dividend data found",
                event="dividend_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"dividend:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Dividend query completed",
            event="dividend_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 6. 融资融券 (PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_margin_trading(self, df: pl.DataFrame) -> int:
        """
        Write margin trading data to database.

        Args:
            df: DataFrame with margin trading data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting margin trading data write",
            event="margin_trading_write_start",
            record_count=len(df),
        )

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
                        r["margin_buy_balance"],
                        r["short_sell_balance"],
                        r["margin_buy_volume"],
                        r["short_sell_volume"],
                    )
                    for r in records
                ],
            )

            self._client.commit()

            logger.info(
                "Margin trading data written successfully",
                event="margin_trading_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "margin_trading", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Margin trading write failed",
                event="margin_trading_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "margin_trading", "status": "failed"}
            )
            raise

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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying margin trading with PIT",
            event="margin_trading_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"margin_trading:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No margin trading data found",
                event="margin_trading_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"margin_trading:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Margin trading query completed",
            event="margin_trading_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 7. 股权质押 (PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_pledge_ratio(self, df: pl.DataFrame) -> int:
        """
        Write pledge ratio data to database.

        Args:
            df: DataFrame with pledge ratio data including PIT columns.

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting pledge ratio data write",
            event="pledge_ratio_write_start",
            record_count=len(df),
        )

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
                        r["pledge_ratio"],
                        r["pledge_shares"],
                        r["total_shares"],
                    )
                    for r in records
                ],
            )

            self._client.commit()

            logger.info(
                "Pledge ratio data written successfully",
                event="pledge_ratio_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "pledge_ratio", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Pledge ratio write failed",
                event="pledge_ratio_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(len(df), {"dataset": "pledge_ratio", "status": "failed"})
            raise

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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying pledge ratio with PIT",
            event="pledge_ratio_query_start",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
        )

        if self._data_cache:
            cache_key = f"pledge_ratio:{instrument_id}:{as_of_date.isoformat()}"
            cached = self._data_cache.get(cache_key)
            if cached is not None:
                return pl.DataFrame(cached)

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

        if not rows:
            logger.debug(
                "No pledge ratio data found",
                event="pledge_ratio_query_not_found",
                instrument_id=instrument_id,
                as_of_date=as_of_date.isoformat(),
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        if self._data_cache:
            cache_key = f"pledge_ratio:{instrument_id}:{as_of_date.isoformat()}"
            self._data_cache.set(cache_key, result.to_dicts())

        logger.debug(
            "Pledge ratio query completed",
            event="pledge_ratio_query_complete",
            instrument_id=instrument_id,
            as_of_date=as_of_date.isoformat(),
            record_count=len(result),
        )

        return result

    # ============================================================================
    # 8. 公司行为 (非 PIT)
    # ============================================================================

    @traced("data.capital_write")
    def write_corporate_actions(self, df: pl.DataFrame) -> int:
        """
        Write corporate actions data to database.

        Args:
            df: DataFrame with corporate actions data (no PIT columns).

        Returns:
            Number of records written.

        Raises:
            Exception: If write operation fails.

        """
        logger.info(
            "Starting corporate actions data write",
            event="corporate_actions_write_start",
            record_count=len(df),
        )

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
                event="corporate_actions_write_complete",
                record_count=len(records),
            )

            M.data_records.add(
                len(records), {"dataset": "corporate_actions", "status": "success"}
            )

            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "Corporate actions write failed",
                event="corporate_actions_write_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                len(df), {"dataset": "corporate_actions", "status": "failed"}
            )
            raise

    @traced("data.capital_query")
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
            Returns empty DataFrame if no data found.

        """
        logger.debug(
            "Querying corporate actions",
            event="corporate_actions_query_start",
            instrument_id=instrument_id,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
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

        # 注意：where_clause 仅由受控的字符串条件构建，无 SQL 注入风险
        rows = self._client.fetchall(
            f"""SELECT instrument_id, action_type, announcement_date,
                       effective_date, description
                FROM corporate_actions
                {where_clause}
                ORDER BY announcement_date DESC""",  # noqa: S608
            params,
        )

        if not rows:
            logger.debug(
                "No corporate actions data found",
                event="corporate_actions_query_not_found",
                instrument_id=instrument_id,
            )
            return pl.DataFrame()

        result = pl.DataFrame(rows)

        logger.debug(
            "Corporate actions query completed",
            event="corporate_actions_query_complete",
            instrument_id=instrument_id,
            record_count=len(result),
        )

        return result

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
