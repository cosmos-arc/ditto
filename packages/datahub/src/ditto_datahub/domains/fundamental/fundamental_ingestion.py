"""
FundamentalIngestion service for Fundamental domain data ingestion.

This module provides the FundamentalIngestion service which orchestrates
the data ingestion flow from Source to Store for the Fundamental domain.

Core functionality:
- ingest_balance_sheet: Ingest balance sheet data
- ingest_income_statement: Ingest income statement data
- ingest_cash_flow: Ingest cash flow data
- ingest_dividend: Ingest dividend data
- ingest_corporate_actions: Ingest corporate actions data
- ingest_forecast: Ingest forecast data
- ingest_express: Ingest express data

Ingestion Flow:
1. Fetch data from Source (SourceSchema format)
2. Validate SourceSchema (already done in Source layer)
3. Write to Store (StoreSchema format)
4. Return IngestionResult

Note: Data transformation from SourceSchema to StoreSchema is handled
by the Store layer, as the Store accepts SourceSchema format data.

Batch Processing:
The CapitalTushareAdapter methods (fetch_balance_sheet, etc.) accept
a single ts_code parameter. This service implements batch processing
by iterating over instrument_ids and concatenating the results.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.fundamental.fundamental_service import FundamentalService
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


class FundamentalIngestion:
    """
    Fundamental domain data ingestion service.

    Orchestrates the complete data ingestion flow from Source to Store
    for Fundamental domain data types.

    Implements batch processing by iterating over multiple instrument_ids
    and calling the single-instrument CapitalTushareAdapter methods.

    Attributes:
        _fundamental_service: FundamentalService instance for data persistence.
        _tushare_source: CapitalTushareAdapter instance for data fetching.

    Examples:
        >>> ingestion = FundamentalIngestion(
        ...     fundamental_service=fundamental_service,
        ...     tushare_source=tushare_source,
        ... )
        >>> result = ingestion.ingest_balance_sheet(
        ...     instrument_ids=["600000.SH", "000001.SZ"],
        ...     start_date="20240101",
        ...     end_date="20240331",
        ... )
        >>> assert result.success

    """

    def __init__(
        self,
        fundamental_service: FundamentalService,
        tushare_source: CapitalTushareAdapter,
    ) -> None:
        """
        Initialize FundamentalIngestion.

        Args:
            fundamental_service: FundamentalService instance for data persistence.
            tushare_source: CapitalTushareAdapter instance for data fetching.

        """
        self._fundamental_service = fundamental_service
        self._tushare_source = tushare_source

        logger.debug(
            "FundamentalIngestion initialized",
            event="fundamental_ingestion_init_complete",
        )

    # ========================================================================
    # 1. 财务报表数据 (PIT)
    # ========================================================================

    @traced("ingestion.fundamental.balance_sheet")
    def ingest_balance_sheet(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入资产负债表数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        """
        try:
            # Batch processing: iterate over instrument_ids and concatenate results
            dfs: list[pl.DataFrame] = []
            for ts_code in instrument_ids:
                df = self._tushare_source.fetch_balance_sheet(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                dfs.append(df)

            # Concatenate all DataFrames
            df = pl.concat(dfs, how="vertical") if dfs else pl.DataFrame()

            write_result = self._fundamental_service.write("balance_sheet", df)
            records_written = write_result.records_written

            M.data_records.add(
                records_written,
                {
                    "dataset": "balance_sheet",
                    "source": "tushare",
                },
            )

            logger.info(
                "Balance sheet data ingested",
                event="balance_sheet_ingestion_complete",
                records=records_written,
            )

            return IngestionResult(
                success=True,
                records_written=records_written,
                dataset="balance_sheet",
            )

        except Exception as e:
            logger.error(
                "Balance sheet ingestion failed",
                event="balance_sheet_ingestion_failed",
                error=str(e),
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="balance_sheet",
                error=str(e),
            )

    @traced("ingestion.fundamental.income_statement")
    def ingest_income_statement(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入利润表数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        """
        try:
            # Batch processing: iterate over instrument_ids and concatenate results
            dfs: list[pl.DataFrame] = []
            for ts_code in instrument_ids:
                df = self._tushare_source.fetch_income_statement(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                dfs.append(df)

            # Concatenate all DataFrames
            df = pl.concat(dfs, how="vertical") if dfs else pl.DataFrame()

            write_result = self._fundamental_service.write("income_statement", df)
            records_written = write_result.records_written

            M.data_records.add(
                records_written,
                {
                    "dataset": "income_statement",
                    "source": "tushare",
                },
            )

            logger.info(
                "Income statement data ingested",
                event="income_statement_ingestion_complete",
                records=records_written,
            )

            return IngestionResult(
                success=True,
                records_written=records_written,
                dataset="income_statement",
            )

        except Exception as e:
            logger.error(
                "Income statement ingestion failed",
                event="income_statement_ingestion_failed",
                error=str(e),
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="income_statement",
                error=str(e),
            )

    @traced("ingestion.fundamental.cash_flow")
    def ingest_cash_flow(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入现金流量表数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        """
        try:
            # Batch processing: iterate over instrument_ids and concatenate results
            dfs: list[pl.DataFrame] = []
            for ts_code in instrument_ids:
                df = self._tushare_source.fetch_cash_flow(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                dfs.append(df)

            # Concatenate all DataFrames
            df = pl.concat(dfs, how="vertical") if dfs else pl.DataFrame()

            write_result = self._fundamental_service.write("cash_flow", df)
            records_written = write_result.records_written

            M.data_records.add(
                records_written,
                {
                    "dataset": "cash_flow",
                    "source": "tushare",
                },
            )

            logger.info(
                "Cash flow data ingested",
                event="cash_flow_ingestion_complete",
                records=records_written,
            )

            return IngestionResult(
                success=True,
                records_written=records_written,
                dataset="cash_flow",
            )

        except Exception as e:
            logger.error(
                "Cash flow ingestion failed",
                event="cash_flow_ingestion_failed",
                error=str(e),
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="cash_flow",
                error=str(e),
            )

    # ========================================================================
    # 2. 公司行为数据
    # ========================================================================

    @traced("ingestion.fundamental.dividend")
    def ingest_dividend(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入分红数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        """
        try:
            # Batch processing: iterate over instrument_ids and concatenate results
            dfs: list[pl.DataFrame] = []
            for ts_code in instrument_ids:
                df = self._tushare_source.fetch_dividend(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                dfs.append(df)

            # Concatenate all DataFrames
            df = pl.concat(dfs, how="vertical") if dfs else pl.DataFrame()

            write_result = self._fundamental_service.write("dividend", df)
            records_written = write_result.records_written

            M.data_records.add(
                records_written,
                {
                    "dataset": "dividend",
                    "source": "tushare",
                },
            )

            logger.info(
                "Dividend data ingested",
                event="dividend_ingestion_complete",
                records=records_written,
            )

            return IngestionResult(
                success=True,
                records_written=records_written,
                dataset="dividend",
            )

        except Exception as e:
            logger.error(
                "Dividend ingestion failed",
                event="dividend_ingestion_failed",
                error=str(e),
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="dividend",
                error=str(e),
            )

    @traced("ingestion.fundamental.corporate_actions")
    def ingest_corporate_actions(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入公司行为数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        """
        try:
            # Batch processing: iterate over instrument_ids and concatenate results
            dfs: list[pl.DataFrame] = []
            for ts_code in instrument_ids:
                df = self._tushare_source.fetch_corporate_actions(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                dfs.append(df)

            # Concatenate all DataFrames
            df = pl.concat(dfs, how="vertical") if dfs else pl.DataFrame()

            write_result = self._fundamental_service.write("corporate_actions", df)
            records_written = write_result.records_written

            M.data_records.add(
                records_written,
                {
                    "dataset": "corporate_actions",
                    "source": "tushare",
                },
            )

            logger.info(
                "Corporate actions data ingested",
                event="corporate_actions_ingestion_complete",
                records=records_written,
            )

            return IngestionResult(
                success=True,
                records_written=records_written,
                dataset="corporate_actions",
            )

        except Exception as e:
            logger.error(
                "Corporate actions ingestion failed",
                event="corporate_actions_ingestion_failed",
                error=str(e),
            )
            return IngestionResult(
                success=False,
                records_written=0,
                dataset="corporate_actions",
                error=str(e),
            )

    # ========================================================================
    # 3. 业绩预告/快报数据
    # ========================================================================

    @traced("ingestion.fundamental.forecast")
    def ingest_forecast(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入业绩预告数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        Note:
            此方法暂时未实现，待 Tushare adapter 中实现 fetch_forecast 方法后完成。

        """
        return IngestionResult(
            success=False,
            records_written=0,
            dataset="forecast",
            error="forecast ingestion not yet implemented in Tushare adapter",
        )

    @traced("ingestion.fundamental.express")
    def ingest_express(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ) -> IngestionResult:
        """
        摄入业绩快报数据.

        Args:
            instrument_ids: 标的 ID 列表。
            start_date: 开始日期 (YYYYMMDD).
            end_date: 结束日期 (YYYYMMDD).

        Returns:
            IngestionResult: 摄入结果.

        Note:
            此方法暂时未实现，待 Tushare adapter 中实现 fetch_express 方法后完成。

        """
        return IngestionResult(
            success=False,
            records_written=0,
            dataset="express",
            error="express ingestion not yet implemented in Tushare adapter",
        )
