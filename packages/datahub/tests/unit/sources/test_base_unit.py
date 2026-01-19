"""Tests for DataSource base classes and exceptions."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.sources.source import (
    DataSource,
    DataSourceError,
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
    SourceTransformationError,
)


class TestDataSourceError:
    """Tests for DataSourceError base class."""

    def test_initialization_with_message_only(self) -> None:
        """Test error initialization with message only."""
        error = DataSourceError("Test error")
        assert str(error) == "Test error"
        assert error.details == {}

    def test_initialization_with_details(self) -> None:
        """Test error initialization with details."""
        error = DataSourceError("Test error", details={"key": "value"})
        assert error.details["key"] == "value"


class TestSourceConfigurationError:
    """Tests for SourceConfigurationError."""

    def test_missing_token(self) -> None:
        """Test error when token is missing."""
        error = SourceConfigurationError(
            message="Token not found",
            env_var="TUSHARE_TOKEN",
        )
        assert error.details["env_var"] == "TUSHARE_TOKEN"

    def test_with_config_key(self) -> None:
        """Test error with config_key parameter."""
        error = SourceConfigurationError(
            message="Invalid config",
            config_key="api_timeout",
        )
        assert error.details["config_key"] == "api_timeout"


class TestSourceAuthenticationError:
    """Tests for SourceAuthenticationError."""

    def test_invalid_credentials(self) -> None:
        """Test error for invalid credentials."""
        error = SourceAuthenticationError(
            message="Authentication failed",
            provider="tushare",
        )
        assert error.details["provider"] == "tushare"

    def test_without_provider(self) -> None:
        """Test error without provider parameter."""
        error = SourceAuthenticationError(message="Auth failed")
        assert error.details == {}


class TestSourceRateLimitError:
    """Tests for SourceRateLimitError."""

    def test_rate_limit_details(self) -> None:
        """Test error includes rate limit details."""
        error = SourceRateLimitError(
            message="Rate limit exceeded",
            provider="tushare",
            limit=200,
            window=60,
        )
        assert error.details["limit"] == 200
        assert error.details["window"] == 60

    def test_partial_details(self) -> None:
        """Test error with partial details."""
        error = SourceRateLimitError(
            message="Too many requests",
            limit=100,
        )
        assert error.details["limit"] == 100
        assert "window" not in error.details


class TestSourceFetchError:
    """Tests for SourceFetchError."""

    def test_fetch_error_with_date(self) -> None:
        """Test error includes fetch context."""
        error = SourceFetchError(
            message="Failed to fetch data",
            provider="tushare",
            dataset="etf_daily",
            trade_date=date(2024, 12, 27),
        )
        assert error.details["dataset"] == "etf_daily"
        assert error.details["trade_date"] == "2024-12-27"

    def test_fetch_error_with_original_error(self) -> None:
        """Test error includes original error message."""
        error = SourceFetchError(
            message="API error",
            original_error="Connection timeout",
        )
        assert error.details["original_error"] == "Connection timeout"


class TestSourceTransformationError:
    """Tests for SourceTransformationError."""

    def test_schema_mismatch(self) -> None:
        """Test error for schema mismatch."""
        error = SourceTransformationError(
            message="Schema validation failed",
            provider="tushare",
            dataset="etf_daily",
            expected_columns=["src_code", "trade_date", "close"],
            actual_columns=["code", "date", "price"],
        )
        assert error.details["expected_columns"] == ["src_code", "trade_date", "close"]
        assert error.details["actual_columns"] == ["code", "date", "price"]

    def test_transformation_error_minimal(self) -> None:
        """Test error with minimal information."""
        error = SourceTransformationError(
            message="Transform failed",
        )
        assert error.details == {}


class TestDataSourceABC:
    """Tests for DataSource abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that DataSource cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DataSource()  # type: ignore[abstract]

    def test_subclass_must_implement_all_methods(self) -> None:
        """Test subclass must implement all abstract methods."""

        class IncompleteProvider(DataSource):
            def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            # Missing fetch_etf_daily

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test complete subclass can be instantiated."""

        class CompleteProvider(DataSource):
            def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_stock_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

        # Should not raise
        provider = CompleteProvider()
        assert isinstance(provider, DataSource)
