"""DataSource abstract base class and exception hierarchy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import polars as pl


class DataSourceError(Exception):
    """DataHub data source base exception."""

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """
        Initialize DataSource error.

        Args:
            message: Error message.
            details: Additional error details.

        """
        super().__init__(message)
        self.details = details or {}


class SourceConfigurationError(DataSourceError):
    """Configuration error (missing env var, invalid settings)."""

    def __init__(
        self,
        message: str = "Source configuration error",
        env_var: str | None = None,
        config_key: str | None = None,
    ) -> None:
        """
        Initialize configuration error.

        Args:
            message: Error message.
            env_var: Environment variable name that is missing.
            config_key: Configuration key that is invalid.

        """
        details: dict[str, object] = {}
        if env_var:
            details["env_var"] = env_var
        if config_key:
            details["config_key"] = config_key
        super().__init__(message, details if details else None)


class SourceAuthenticationError(DataSourceError):
    """Authentication failure (invalid token, credentials)."""

    def __init__(
        self,
        message: str = "Authentication failed",
        source: str | None = None,
    ) -> None:
        """
        Initialize authentication error.

        Args:
            message: Error message.
            source: Data source identifier.

        """
        details: dict[str, object] = {}
        if source:
            details["source"] = source
        super().__init__(message, details if details else None)


class SourceRateLimitError(DataSourceError):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        source: str | None = None,
        limit: int | None = None,
        window: int | None = None,
    ) -> None:
        """
        Initialize rate limit error.

        Args:
            message: Error message.
            source: Data source identifier.
            limit: Request limit.
            window: Time window in seconds.

        """
        details: dict[str, object] = {}
        if source:
            details["source"] = source
        if limit:
            details["limit"] = limit
        if window:
            details["window"] = window
        super().__init__(message, details if details else None)


class SourceFetchError(DataSourceError):
    """Data fetch failure (network error, API error)."""

    def __init__(
        self,
        message: str = "Failed to fetch data",
        source: str | None = None,
        dataset: str | None = None,
        trade_date: date | None = None,
        original_error: str | None = None,
    ) -> None:
        """
        Initialize fetch error.

        Args:
            message: Error message.
            source: Data source identifier.
            dataset: Dataset name.
            trade_date: Trade date being fetched.
            original_error: Original error message.

        """
        details: dict[str, object] = {}
        if source:
            details["source"] = source
        if dataset:
            details["dataset"] = dataset
        if trade_date:
            details["trade_date"] = trade_date.isoformat()
        if original_error:
            details["original_error"] = original_error
        super().__init__(message, details if details else None)


class SourceTransformationError(DataSourceError):
    """Data transformation error (schema mismatch, conversion failure)."""

    def __init__(
        self,
        message: str = "Data transformation failed",
        source: str | None = None,
        dataset: str | None = None,
        expected_columns: list[str] | None = None,
        actual_columns: list[str] | None = None,
    ) -> None:
        """
        Initialize transformation error.

        Args:
            message: Error message.
            source: Data source identifier.
            dataset: Dataset name.
            expected_columns: Expected column names.
            actual_columns: Actual column names received.

        """
        details: dict[str, object] = {}
        if source:
            details["source"] = source
        if dataset:
            details["dataset"] = dataset
        if expected_columns:
            details["expected_columns"] = expected_columns
        if actual_columns:
            details["actual_columns"] = actual_columns
        super().__init__(message, details if details else None)


class DataSource(ABC):
    """Abstract base class for external data sources."""

    @abstractmethod
    def fetch_calendar(
        self,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch trading calendar.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - trade_date: Date
            - is_open: Boolean

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_etf_basic(self) -> pl.DataFrame:
        """
        Fetch ETF basic information.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "510300.SH")
            - ticker: Display ticker (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_index_basic(self) -> pl.DataFrame:
        """
        Fetch index basic information.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SH")
            - ticker: Display ticker (e.g., "000001")
            - name: Index name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch ETF daily OHLCV bars.

        Supports two query modes:
        - By date (batch): Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "510300.SH").
            start_date: Start date (YYYY-MM-DD). Required with source_ticker.
            end_date: End date (YYYY-MM-DD). Required with source_ticker.

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        pass

    @abstractmethod
    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch index daily OHLCV bars.

        Supports two query modes:
        - By date (batch): Specify trade_date (optionally with ts_codes filter)
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            ts_codes: List of ts_codes (e.g., ["000001.SH", "399001.SZ"]).
                Only used with trade_date mode.
            source_ticker: Source code (e.g., "000001.SH").
            start_date: Start date (YYYY-MM-DD). Required with source_ticker.
            end_date: End date (YYYY-MM-DD). Required with source_ticker.

        Returns:
            DataFrame with columns (matching INDEX_DAILY_SCHEMA):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        pass

    @abstractmethod
    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Supports two modes:
        - Batch mode: No source_ticker, fetch all stocks (all listing statuses)
        - Single mode: With source_ticker, fetch specific stock

        Args:
            source_ticker: Stock code (e.g., "600519.SH"). Optional.
                If not provided, fetches all stocks.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code (e.g., "000001.SZ")
            - ticker: Display ticker (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code (SSE/SZSE/BSE)
            - list_date: Listing date
            - list_status: Listing status (L=Active, D=Delisted, P=Suspended)
            Empty DataFrame if single stock not found.

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Supports two query modes:
        - By date (batch): Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Required with source_ticker.
            end_date: End date (YYYY-MM-DD). Required with source_ticker.

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - source_ticker: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        pass

    @abstractmethod
    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - source_ticker: Source code
            - trade_date: Date
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "510300.SH").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with columns:
            - source_ticker: Source code
            - trade_date: Date
            - adj_factor: Float64

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock status information.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - source_ticker: Source code
            - trade_date: Date
            - is_suspended: Boolean
            - suspend_timing: Utf8
            - is_st: Boolean
            - st_type: Utf8
            - list_status: Utf8

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch balance sheet data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with balance_sheet SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch income statement data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with income_statement SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch cash flow data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with cash_flow SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch dividend data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with dividend SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch valuation metrics data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with valuation_metrics SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch margin trading data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with margin_trading SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        Fetch pledge ratio data.

        Supports two query modes:
        - By date batch: Specify trade_date
        - By ticker + date range: Specify source_ticker + start_date + end_date

        Args:
            trade_date: Trade date (YYYY-MM-DD). Mutually exclusive with source_ticker.
            source_ticker: Source code (e.g., "000001.SZ").
            start_date: Start date (YYYY-MM-DD). Used with source_ticker.
            end_date: End date (YYYY-MM-DD). Used with source_ticker.

        Returns:
            DataFrame with pledge_ratio SourceSchema fields.

        Raises:
            ValueError: Invalid parameter combination.
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch macro indicators data.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with macro_indicators SourceSchema fields.

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch corporate actions data.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with corporate_actions SourceSchema fields.

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        """
        获取申万行业分类.

        Args:
            level: 行业级别 (1=一级行业, 2=二级行业).

        Returns:
            DataFrame with columns:
            - source_ticker: 行业代码 (e.g., "801010.SI")
            - industry_name: 行业名称
            - level: 行业级别 (1 or 2)

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch FX (Foreign Exchange) daily OHLCV bars.

        Args:
            ts_codes: FX ticker codes (e.g., ["USDCNH.FXCM"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with FX_SOURCE_SCHEMA columns:
            - instrument_id: Internal instrument ID
            - trade_date: Trade date (Date)
            - trade_date_utc: Trade date in UTC (Datetime)
            - open, high, low, close: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        """
        Fetch commodity daily prices.

        Args:
            codes: Commodity codes (e.g., ["COMMOD_WTI", "COMMOD_GOLD"]).
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            DataFrame with COMMODITY_SOURCE_SCHEMA columns:
            - instrument_id: Internal instrument ID
            - trade_date: Trade date (Date)
            - trade_date_utc: Trade date in UTC (Datetime)
            - open, high, low, close: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass


__all__ = [
    "DataSource",
    "DataSourceError",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceTransformationError",
]
