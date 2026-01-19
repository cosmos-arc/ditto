"""Tests for DataProvider base classes and exceptions."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.providers.provider import (
    DataProvider,
    DataProviderError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderFetchError,
    ProviderRateLimitError,
    ProviderTransformationError,
)


class TestDataProviderError:
    """Tests for DataProviderError base class."""

    def test_initialization_with_message_only(self) -> None:
        """Test error initialization with message only."""
        error = DataProviderError("Test error")
        assert str(error) == "Test error"
        assert error.details == {}

    def test_initialization_with_details(self) -> None:
        """Test error initialization with details."""
        error = DataProviderError("Test error", details={"key": "value"})
        assert error.details["key"] == "value"


class TestProviderConfigurationError:
    """Tests for ProviderConfigurationError."""

    def test_missing_token(self) -> None:
        """Test error when token is missing."""
        error = ProviderConfigurationError(
            message="Token not found",
            env_var="TUSHARE_TOKEN",
        )
        assert error.details["env_var"] == "TUSHARE_TOKEN"

    def test_with_config_key(self) -> None:
        """Test error with config_key parameter."""
        error = ProviderConfigurationError(
            message="Invalid config",
            config_key="api_timeout",
        )
        assert error.details["config_key"] == "api_timeout"


class TestProviderAuthenticationError:
    """Tests for ProviderAuthenticationError."""

    def test_invalid_credentials(self) -> None:
        """Test error for invalid credentials."""
        error = ProviderAuthenticationError(
            message="Authentication failed",
            provider="tushare",
        )
        assert error.details["provider"] == "tushare"

    def test_without_provider(self) -> None:
        """Test error without provider parameter."""
        error = ProviderAuthenticationError(message="Auth failed")
        assert error.details == {}


class TestProviderRateLimitError:
    """Tests for ProviderRateLimitError."""

    def test_rate_limit_details(self) -> None:
        """Test error includes rate limit details."""
        error = ProviderRateLimitError(
            message="Rate limit exceeded",
            provider="tushare",
            limit=200,
            window=60,
        )
        assert error.details["limit"] == 200
        assert error.details["window"] == 60

    def test_partial_details(self) -> None:
        """Test error with partial details."""
        error = ProviderRateLimitError(
            message="Too many requests",
            limit=100,
        )
        assert error.details["limit"] == 100
        assert "window" not in error.details


class TestProviderFetchError:
    """Tests for ProviderFetchError."""

    def test_fetch_error_with_date(self) -> None:
        """Test error includes fetch context."""
        error = ProviderFetchError(
            message="Failed to fetch data",
            provider="tushare",
            dataset="etf_daily",
            trade_date=date(2024, 12, 27),
        )
        assert error.details["dataset"] == "etf_daily"
        assert error.details["trade_date"] == "2024-12-27"

    def test_fetch_error_with_original_error(self) -> None:
        """Test error includes original error message."""
        error = ProviderFetchError(
            message="API error",
            original_error="Connection timeout",
        )
        assert error.details["original_error"] == "Connection timeout"


class TestProviderTransformationError:
    """Tests for ProviderTransformationError."""

    def test_schema_mismatch(self) -> None:
        """Test error for schema mismatch."""
        error = ProviderTransformationError(
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
        error = ProviderTransformationError(
            message="Transform failed",
        )
        assert error.details == {}


class TestDataProviderABC:
    """Tests for DataProvider abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that DataProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DataProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_all_methods(self) -> None:
        """Test subclass must implement all abstract methods."""

        class IncompleteProvider(DataProvider):
            def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            # Missing fetch_etf_daily

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test complete subclass can be instantiated."""

        class CompleteProvider(DataProvider):
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
        assert isinstance(provider, DataProvider)
