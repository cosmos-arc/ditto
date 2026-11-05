"""Fundamental domain store with dedicated get/save methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import OnDuplicate, logger

from ditto_data.services.deps import FundamentalReaders, FundamentalWriters


class FundamentalStore:
    """
    Fundamental domain unified service.

    Thin wrapper with dependency injection using CQRS pattern.
    Delegates read operations to Readers and write operations to Writers.

    跨年分片与同年分区写入锁统一收口在 ParquetDatasetWriter.write
    （审计 #684 批B #7/#14）。
    """

    def __init__(
        self,
        read_ports: FundamentalReaders,
        write_ports: FundamentalWriters,
    ) -> None:
        """
        Initialize FundamentalStore with CQRS Readers/Writers.

        Args:
            read_ports: Fundamental 域读取依赖（包含所有 Reader）.
            write_ports: Fundamental 域写入依赖（包含所有 Writer）.

        """
        self._read_ports = read_ports
        self._write_ports = write_ports

        logger.debug(
            "FundamentalStore initialized with CQRS Readers/Writers",
            event="fundamental_store_init_complete",
        )

    # get_* - Single record queries (PIT)

    def get_balance_sheet(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get balance sheet for instrument on date (PIT query)."""
        df = self._read_ports.balance_sheet.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_income_statement(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get income statement for instrument on date (PIT query)."""
        df = self._read_ports.income_statement.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_cash_flow(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get cash flow for instrument on date (PIT query)."""
        df = self._read_ports.cash_flow.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    def get_dividend(self, instrument_id: int, as_of_date: date) -> pl.DataFrame | None:
        """Get dividend data for instrument on date (PIT query)."""
        df = self._read_ports.dividend.get(instrument_id, as_of_date)
        return None if df.is_empty() else df

    # list_* - Multi record queries

    def get_fina_indicator(
        self,
        instrument_id: int,
        start: str,
        end: str,
        as_of: str | None = None,
    ) -> pl.DataFrame:
        """
        逐标的财务指标窗口读（report_date 窗口；118 列透传）.

        knowledge_date=公告日 ann_date;as_of 给定时按 knowledge_date<=as_of
        收敛到最新公告版本（修订选版）。
        """
        reader = self._read_ports.fina_indicator
        if reader is None:
            raise ValueError("fina_indicator reader not configured")
        frame = reader.read(
            instrument_ids=[instrument_id],
            start_date=start,
            end_date=end,
            filters=(
                [pl.col("knowledge_date") <= pl.lit(as_of).str.to_date()]
                if as_of
                else None
            ),
        )
        if frame.is_empty():
            return frame
        if as_of:
            # pit_asof 词表:同 (instrument, report_date) 收敛到最新可见
            # knowledge 版本(修订选版,#628)。
            frame = frame.sort("knowledge_date").unique(
                subset=["instrument_id", "report_date"], keep="last"
            )
        return frame.sort(["report_date", "knowledge_date"])

    def get_earnings_express(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """
        逐标的业绩快报窗口读（ann_date 窗口=公告事件;金额元）.

        平日 0 行=无公告正常;audit_status 透出不伪称已审计。
        instrument_column=source_ticker（该库以 ticker 为仪器键过滤）。
        """
        reader = self._read_ports.earnings_express
        if reader is None:
            raise ValueError("earnings_express reader not configured")
        # ParquetDatasetReader 的 instrument 过滤恒作用于 instrument_id 列,
        # 该库仪器键是 source_ticker——经 filters 显式过滤。
        frame = reader.read(
            start_date=start,
            end_date=end,
            filters=[pl.col("source_ticker") == source_ticker],
        )
        return frame if frame.is_empty() else frame.sort("ann_date")

    def get_earnings_forecast(
        self, source_ticker: str, start: str, end: str
    ) -> pl.DataFrame:
        """逐标的业绩预告窗口读（ann_date 窗口;净利润上下界万元）."""
        reader = self._read_ports.earnings_forecast
        if reader is None:
            raise ValueError("earnings_forecast reader not configured")
        frame = reader.read(
            start_date=start,
            end_date=end,
            filters=[pl.col("source_ticker") == source_ticker],
        )
        return frame if frame.is_empty() else frame.sort(["ann_date", "report_date"])

    def list_corporate_actions(
        self,
        instrument_id: int,
        start_date: date,
        end_date: date,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """List corporate actions for instrument in date range (with optional PIT)."""
        return self._read_ports.corporate_actions.query(
            instrument_id, start_date, end_date, as_of_date
        )

    # save_* - Write methods

    def save_balance_sheet(self, df: pl.DataFrame) -> int:
        """Save balance sheet data."""
        return self._write_ports.balance_sheet.write(df)

    def save_income_statement(self, df: pl.DataFrame) -> int:
        """Save income statement data."""
        return self._write_ports.income_statement.write(df)

    def save_cash_flow(self, df: pl.DataFrame) -> int:
        """Save cash flow data."""
        return self._write_ports.cash_flow.write(df)

    def save_dividend(self, df: pl.DataFrame) -> int:
        """Save dividend data."""
        return self._write_ports.dividend.write(df)

    def save_corporate_actions(self, df: pl.DataFrame) -> int:
        """Save corporate actions data."""
        return self._write_ports.corporate_actions.write(df)

    # #434 业绩预告/快报：parquet 公告事件写入（无公告时刻，采集日即知识日；
    # 与 sqlite 写路径共享单活摄取不变量，写入锁由 writer 层统一提供）。

    def save_earnings_forecast(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save earnings-forecast announcement rows (net-profit bounds in 万元)."""
        writer = self._write_ports.earnings_forecast
        if writer is None:
            raise ValueError("earnings_forecast writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_earnings_express(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save earnings-express announcement rows (amounts in 元)."""
        writer = self._write_ports.earnings_express
        if writer is None:
            raise ValueError("earnings_express writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_fina_indicator(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        Save official financial-indicator rows (#521, 118 列透传).

        行按 report_date 年分片落各自的年分区（correctness review #3）：
        摄取日年与报告期年跨年时（8 季度超集常态），单一摄取年分区会让
        按报告期年的范围读漏行。分片由 ParquetDatasetWriter 统一处理。
        """
        writer = self._write_ports.fina_indicator
        if writer is None:
            raise ValueError("fina_indicator writer not configured")
        if df.is_empty():
            return 0
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_fund_portfolio(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """
        Save fund quarterly holding rows (#522, 公告日驱动).

        同 fina_indicator：按 report_date 年分片写（correctness review #3），
        分片由 ParquetDatasetWriter 统一处理。
        """
        writer = self._write_ports.fund_portfolio
        if writer is None:
            raise ValueError("fund_portfolio writer not configured")
        if df.is_empty():
            return 0
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated
