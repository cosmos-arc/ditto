"""
CapitalIngestion service for Capital domain data ingestion.

This module provides the CapitalIngestion service which orchestrates
the data ingestion flow from Source to Store for the Capital domain.

Core functionality:
- ingest_balance_sheet: Ingest balance sheet data
- ingest_income_statement: Ingest income statement data
- ingest_cash_flow: Ingest cash flow data
- ingest_valuation_metrics: Ingest valuation metrics data
- ingest_dividend: Ingest dividend data
- ingest_margin_trading: Ingest margin trading data
- ingest_pledge_ratio: Ingest pledge ratio data
- ingest_futures: Ingest futures data
- ingest_index_composition: Ingest index composition data
- ingest_corporate_actions: Ingest corporate actions data

Ingestion Flow:
1. Fetch data from Source (SourceSchema format)
2. Validate SourceSchema (already done in Source layer)
3. Write to Store (StoreSchema format)
4. Return IngestionResult

Note: Data transformation from SourceSchema to StoreSchema is handled
by the Store layer, as the Store accepts SourceSchema format data.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.capital.capital_store import CapitalStore
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter


@dataclass(frozen=True)
class IngestionResult:
    """
    Data ingestion result.

    Attributes:
        success: Whether ingestion was successful.
        records_written: Number of records written to store.
        dataset: Dataset name.
        error: Error message if ingestion failed.

    """

    success: bool
    records_written: int
    dataset: str
    error: str | None = None


class CapitalIngestion:
    """
    Capital domain data ingestion service.

    Orchestrates the complete data ingestion flow from Source to Store
    for Capital domain data types.

    Attributes:
        _capital_store: CapitalStore instance for data persistence.
        _tushare_source: CapitalTushareAdapter instance for data fetching.

    Examples:
        >>> ingestion = CapitalIngestion(
        ...     capital_store=capital_store,
        ...     tushare_source=tushare_source,
        ... )
        >>> result = ingestion.ingest_balance_sheet(
        ...     instrument_ids=["600000.SH"],
        ...     start_date="20240101",
        ...     end_date="20240331",
        ... )
        >>> assert result.success

    """

    def __init__(
        self,
        capital_store: CapitalStore,
        tushare_source: CapitalTushareAdapter,
    ) -> None:
        """
        Initialize CapitalIngestion.

        Args:
            capital_store: CapitalStore instance for data persistence.
            tushare_source: CapitalTushareAdapter instance for data fetching.

        """
        self._capital_store = capital_store
        self._tushare_source = tushare_source

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _ingest_financial_data(
        self,
        dataset_name: str,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
        fetch_method: Callable[..., pl.DataFrame],
        write_method: Callable[[pl.DataFrame], int],
    ) -> IngestionResult:
        """
        Generic method for ingesting financial data.

        Args:
            dataset_name: Name of the dataset (e.g., "balance_sheet").
            instrument_ids: List of instrument IDs to ingest.
            start_date: Start date (YYYYMMDD).
            end_date: End date (YYYYMMDD).
            fetch_method: Source method to fetch data.
            write_method: Store method to write data.

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            f"Starting {dataset_name} ingestion",
            event=f"{dataset_name}_ingestion_start",
            instrument_count=len(instrument_ids),
            start_date=start_date,
            end_date=end_date,
        )

        all_data: list[pl.DataFrame] = []

        # Fetch data for each instrument
        for instrument_id in instrument_ids:
            try:
                # Fetch from Source (SourceSchema format, already validated)
                df = fetch_method(
                    ts_code=instrument_id,
                    start_date=start_date,
                    end_date=end_date,
                )

                if df.is_empty():
                    logger.debug(
                        f"No {dataset_name} data found for instrument",
                        event=f"{dataset_name}_no_data",
                        instrument_id=instrument_id,
                    )
                    continue

                all_data.append(df)

            except Exception as e:
                logger.error(
                    f"Failed to fetch {dataset_name} data",
                    event=f"{dataset_name}_fetch_failed",
                    instrument_id=instrument_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                return IngestionResult(
                    success=False,
                    records_written=0,
                    dataset=dataset_name,
                    error=f"Failed to fetch data for {instrument_id}: {e}",
                )

        # Write to Store
        if all_data:
            try:
                combined_df = pl.concat(all_data)
                total_records = write_method(combined_df)

                logger.info(
                    f"{dataset_name.capitalize()} ingestion completed successfully",
                    event=f"{dataset_name}_ingestion_complete",
                    records_written=total_records,
                )

                M.data_records.add(
                    total_records,
                    {"dataset": dataset_name, "status": "success"},
                )

                return IngestionResult(
                    success=True,
                    records_written=total_records,
                    dataset=dataset_name,
                )

            except Exception as e:
                logger.error(
                    f"Failed to write {dataset_name} data",
                    event=f"{dataset_name}_write_failed",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                M.data_records.add(
                    0,
                    {"dataset": dataset_name, "status": "failed"},
                )
                return IngestionResult(
                    success=False,
                    records_written=0,
                    dataset=dataset_name,
                    error=f"Failed to write data: {e}",
                )

        # No data to write
        logger.info(
            f"No {dataset_name} data to write",
            event=f"{dataset_name}_ingestion_empty",
        )
        return IngestionResult(
            success=True,
            records_written=0,
            dataset=dataset_name,
        )

    # ========================================================================
    # 1. 财务报表数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.balance_sheet")
    def ingest_balance_sheet(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        Ingest balance sheet data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest.
            start_date: Start date (YYYYMMDD).
            end_date: End date (YYYYMMDD).

        Returns:
            IngestionResult with success status and records written.

        Examples:
            >>> result = ingestion.ingest_balance_sheet(
            ...     instrument_ids=["600000.SH"],
            ...     start_date="20240101",
            ...     end_date="20240331",
            ... )
            >>> assert result.success

        """
        return self._ingest_financial_data(
            dataset_name="balance_sheet",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
            fetch_method=self._tushare_source.fetch_balance_sheet,
            write_method=self._capital_store.write_balance_sheet,
        )

    @traced("ingestion.capital.income_statement")
    def ingest_income_statement(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        Ingest income statement data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest.
            start_date: Start date (YYYYMMDD).
            end_date: End date (YYYYMMDD).

        Returns:
            IngestionResult with success status and records written.

        """
        return self._ingest_financial_data(
            dataset_name="income_statement",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
            fetch_method=self._tushare_source.fetch_income_statement,
            write_method=self._capital_store.write_income_statement,
        )

    @traced("ingestion.capital.cash_flow")
    def ingest_cash_flow(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        Ingest cash flow data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest.
            start_date: Start date (YYYYMMDD).
            end_date: End date (YYYYMMDD).

        Returns:
            IngestionResult with success status and records written.

        """
        return self._ingest_financial_data(
            dataset_name="cash_flow",
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
            fetch_method=self._tushare_source.fetch_cash_flow,
            write_method=self._capital_store.write_cash_flow,
        )

    # ========================================================================
    # 2. 估值指标数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.valuation_metrics")
    def ingest_valuation_metrics(
        self,
        instrument_ids: list[str] | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest valuation metrics data (PE/PB/PS).

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            trade_date: Trade date (YYYYMMDD) (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting valuation metrics ingestion",
            event="valuation_metrics_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_valuation_metrics(
                ts_code=instrument_ids[0] if instrument_ids else None,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No valuation metrics data to write",
                    event="valuation_metrics_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="valuation_metrics",
                )

            # Write to Store
            total_records = self._capital_store.write_valuation_metrics(df)

            logger.info(
                "Valuation metrics ingestion completed successfully",
                event="valuation_metrics_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "valuation_metrics", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="valuation_metrics",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest valuation metrics data",
                event="valuation_metrics_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "valuation_metrics", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="valuation_metrics",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 3. 股息分红数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.dividend")
    def ingest_dividend(
        self,
        instrument_ids: list[str] | None = None,
        ex_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest dividend data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            ex_date: Ex-dividend date (YYYYMMDD) (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting dividend ingestion",
            event="dividend_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_dividend(
                ts_code=instrument_ids[0] if instrument_ids else None,
                ex_date=ex_date,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No dividend data to write",
                    event="dividend_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="dividend",
                )

            # Write to Store
            total_records = self._capital_store.write_dividend(df)

            logger.info(
                "Dividend ingestion completed successfully",
                event="dividend_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "dividend", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="dividend",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest dividend data",
                event="dividend_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "dividend", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="dividend",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 4. 融资融券数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.margin_trading")
    def ingest_margin_trading(
        self,
        instrument_ids: list[str] | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest margin trading data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            trade_date: Trade date (YYYYMMDD) (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting margin trading ingestion",
            event="margin_trading_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_margin_trading(
                ts_code=instrument_ids[0] if instrument_ids else None,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No margin trading data to write",
                    event="margin_trading_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="margin_trading",
                )

            # Write to Store
            total_records = self._capital_store.write_margin_trading(df)

            logger.info(
                "Margin trading ingestion completed successfully",
                event="margin_trading_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "margin_trading", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="margin_trading",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest margin trading data",
                event="margin_trading_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "margin_trading", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="margin_trading",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 5. 股权质押数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.pledge_ratio")
    def ingest_pledge_ratio(
        self,
        instrument_ids: list[str] | None = None,
        report_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest pledge ratio data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            report_date: Report date (YYYYMMDD) (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting pledge ratio ingestion",
            event="pledge_ratio_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_pledge_ratio(
                ts_code=instrument_ids[0] if instrument_ids else None,
                report_date=report_date,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No pledge ratio data to write",
                    event="pledge_ratio_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="pledge_ratio",
                )

            # Write to Store
            total_records = self._capital_store.write_pledge_ratio(df)

            logger.info(
                "Pledge ratio ingestion completed successfully",
                event="pledge_ratio_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "pledge_ratio", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="pledge_ratio",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest pledge ratio data",
                event="pledge_ratio_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "pledge_ratio", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="pledge_ratio",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 6. 期货数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.futures")
    def ingest_futures(
        self,
        instrument_ids: list[str] | None = None,
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest futures data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            trade_date: Trade date (YYYYMMDD) (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting futures ingestion",
            event="futures_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_futures(
                ts_code=instrument_ids[0] if instrument_ids else None,
                trade_date=trade_date,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No futures data to write",
                    event="futures_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="futures",
                )

            # Write to Store
            total_records = self._capital_store.write_futures(df)

            logger.info(
                "Futures ingestion completed successfully",
                event="futures_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "futures", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="futures",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest futures data",
                event="futures_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "futures", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="futures",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 7. 指数成分股数据 (PIT)
    # ========================================================================

    @traced("ingestion.capital.index_composition")
    def ingest_index_composition(
        self,
        index_id: str,
        asof_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest index composition data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            index_id: Index identifier (e.g., "000001.SH").
            asof_date: Historical query date (YYYY-MM-DD), None for latest.

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting index composition ingestion",
            event="index_composition_ingestion_start",
            index_id=index_id,
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_index_composition(
                index_code=index_id,
                asof_date=asof_date,
            )

            if df.is_empty():
                logger.info(
                    "No index composition data to write",
                    event="index_composition_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="index_composition",
                )

            # Write to Store
            total_records = self._capital_store.write_index_composition(df)

            logger.info(
                "Index composition ingestion completed successfully",
                event="index_composition_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "index_composition", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="index_composition",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest index composition data",
                event="index_composition_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "index_composition", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="index_composition",
                error=f"Failed to ingest data: {e}",
            )

    # ========================================================================
    # 8. 公司行为数据 (非 PIT)
    # ========================================================================

    @traced("ingestion.capital.corporate_actions")
    def ingest_corporate_actions(
        self,
        instrument_ids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> IngestionResult:
        """
        Ingest corporate actions data.

        Flow:
        1. Fetch data from Tushare Source (SourceSchema format)
        2. Validate SourceSchema (already done in Source layer)
        3. Write to CapitalStore

        Args:
            instrument_ids: List of instrument IDs to ingest (optional).
            start_date: Start date (YYYYMMDD) (optional).
            end_date: End date (YYYYMMDD) (optional).

        Returns:
            IngestionResult with success status and records written.

        """
        logger.info(
            "Starting corporate actions ingestion",
            event="corporate_actions_ingestion_start",
        )

        try:
            # Fetch from Source
            df = self._tushare_source.fetch_corporate_actions(
                ts_code=instrument_ids[0] if instrument_ids else None,
                start_date=start_date,
                end_date=end_date,
            )

            if df.is_empty():
                logger.info(
                    "No corporate actions data to write",
                    event="corporate_actions_ingestion_empty",
                )
                return IngestionResult(
                    success=True,
                    records_written=0,
                    dataset="corporate_actions",
                )

            # Write to Store
            total_records = self._capital_store.write_corporate_actions(df)

            logger.info(
                "Corporate actions ingestion completed successfully",
                event="corporate_actions_ingestion_complete",
                records_written=total_records,
            )

            M.data_records.add(
                total_records,
                {"dataset": "corporate_actions", "status": "success"},
            )

            return IngestionResult(
                success=True,
                records_written=total_records,
                dataset="corporate_actions",
            )

        except Exception as e:
            logger.error(
                "Failed to ingest corporate actions data",
                event="corporate_actions_ingestion_failed",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            M.data_records.add(
                0,
                {"dataset": "corporate_actions", "status": "failed"},
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="corporate_actions",
                error=f"Failed to ingest data: {e}",
            )
