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
            - src_code: Source code (e.g., "510300.SH")
            - symbol: Display symbol (e.g., "510300")
            - name: ETF name
            - exchange: Exchange code
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (matching ETF_DAILY_SCHEMA):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
            SourceFetchError: If fetch fails.
            SourceTransformationError: If data transformation fails.

        """
        pass

    @abstractmethod
    def fetch_stock_basic(self) -> pl.DataFrame:
        """
        Fetch stock basic information.

        Returns:
            DataFrame with columns:
            - src_code: Source code (e.g., "000001.SZ")
            - symbol: Display symbol (e.g., "000001")
            - name: Stock name
            - exchange: Exchange code (SSE/SZSE/BSE)
            - list_date: Listing date

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch stock daily OHLCV bars.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns (same as ETF daily schema):
            - src_code: Source code
            - trade_date: Date
            - open, high, low, close, pre_close: Float64
            - volume, amount: Float64
            - pct_change: Float64

        Raises:
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
            - src_code: Source code
            - trade_date: Date
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass

    @abstractmethod
    def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
        """
        Fetch ETF/fund adjustment factors.

        Args:
            trade_date: Trade date (YYYY-MM-DD).

        Returns:
            DataFrame with columns:
            - src_code: Source code
            - trade_date: Date
            - adj_factor: Float64

        Raises:
            SourceFetchError: If fetch fails.

        """
        pass
