"""Protocols for ingestion service dependencies."""

from __future__ import annotations

from typing import Protocol

import polars as pl


class IngestionDataSource(Protocol):
    """Source protocol required by IngestionCoordinator."""

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch calendar data."""
        ...

    def fetch_stock_basic(self) -> pl.DataFrame:
        """Fetch stock basic data."""
        ...

    def fetch_etf_basic(self) -> pl.DataFrame:
        """Fetch ETF basic data."""
        ...

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock daily data."""
        ...

    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """Fetch ETF daily data."""
        ...

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock adjustment factors."""
        ...

    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """Fetch fund adjustment factors."""
        ...

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """Fetch stock status data."""
        ...

    def fetch_balance_sheet(self, trade_date: str) -> pl.DataFrame:
        """Fetch balance sheet data."""
        ...

    def fetch_income_statement(self, trade_date: str) -> pl.DataFrame:
        """Fetch income statement data."""
        ...

    def fetch_cash_flow(self, trade_date: str) -> pl.DataFrame:
        """Fetch cash flow data."""
        ...

    def fetch_dividend(self, trade_date: str) -> pl.DataFrame:
        """Fetch dividend data."""
        ...

    def fetch_valuation_metrics(self, trade_date: str) -> pl.DataFrame:
        """Fetch valuation metrics data."""
        ...

    def fetch_margin_trading(self, trade_date: str) -> pl.DataFrame:
        """Fetch margin trading data."""
        ...

    def fetch_pledge_ratio(self, trade_date: str) -> pl.DataFrame:
        """Fetch pledge ratio data."""
        ...
