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
    # 与 sqlite 写路径共享单活摄取不变量，不加独立文件锁）。

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
        """Save official financial-indicator rows (#521, 118 列透传)."""
        writer = self._write_ports.fina_indicator
        if writer is None:
            raise ValueError("fina_indicator writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_fund_portfolio(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save fund quarterly holding rows (#522, 公告日驱动)."""
        writer = self._write_ports.fund_portfolio
        if writer is None:
            raise ValueError("fund_portfolio writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated
