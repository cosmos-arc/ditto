"""Unit tests for data module exceptions."""

from typing import cast

import pytest
from ditto_core.data.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataSourceError,
    NetworkError,
    RateLimitError,
    ValidationError,
)


class TestDataSourceError:
    """Test cases for DataSourceError base exception."""

    def test_init_with_message_only(self) -> None:
        """Test initialization with only message."""
        error = DataSourceError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.source is None
        assert error.symbol is None
        assert error.extra == {}

    def test_init_with_all_parameters(self) -> None:
        """Test initialization with all parameters."""
        error = DataSourceError(
            message="Test error",
            source="tushare",
            symbol="510300.SH",
            extra_field="extra_value",
        )
        assert str(error) == "Test error"
        assert error.source == "tushare"
        assert error.symbol == "510300.SH"
        assert error.extra["extra_field"] == "extra_value"

    def test_inheritance(self) -> None:
        """Test that DataSourceError inherits from Exception."""
        error = DataSourceError("Test")
        assert isinstance(error, Exception)


class TestNetworkError:
    """Test cases for NetworkError."""

    def test_inheritance(self) -> None:
        """Test that NetworkError inherits from DataSourceError."""
        error: NetworkError = NetworkError("Network error", source="tushare")
        assert isinstance(error, DataSourceError)
        assert isinstance(error, Exception)
        assert str(error) == "Network error"
        # Cast to DataSourceError to access the source attribute
        data_source_error = cast(DataSourceError, error)
        assert data_source_error.source == "tushare"


class TestValidationError:
    """Test cases for ValidationError."""

    def test_inheritance(self) -> None:
        """Test that ValidationError inherits from DataSourceError."""
        error = ValidationError("Invalid data", source="akshare", symbol="159919.SZ")
        assert isinstance(error, DataSourceError)
        assert str(error) == "Invalid data"
        assert error.source == "akshare"
        assert error.symbol == "159919.SZ"


class TestConfigurationError:
    """Test cases for ConfigurationError."""

    def test_inheritance(self) -> None:
        """Test that ConfigurationError inherits from DataSourceError."""
        error = ConfigurationError("Missing API key")
        assert isinstance(error, DataSourceError)
        assert str(error) == "Missing API key"


class TestAuthenticationError:
    """Test cases for AuthenticationError."""

    def test_inheritance(self) -> None:
        """Test that AuthenticationError inherits from DataSourceError."""
        error = AuthenticationError("Invalid token")
        assert isinstance(error, DataSourceError)
        assert str(error) == "Invalid token"


class TestRateLimitError:
    """Test cases for RateLimitError."""

    def test_inheritance(self) -> None:
        """Test that RateLimitError inherits from DataSourceError."""
        error = RateLimitError("Too many requests")
        assert isinstance(error, DataSourceError)
        assert str(error) == "Too many requests"


class TestExceptionChaining:
    """Test exception chaining with custom exceptions."""

    def test_exception_chaining(self) -> None:
        """Test that exceptions can be chained using 'from' syntax."""
        original_error = ValueError("Original error")

        # Test raising with from
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError("Wrapped error", source="test") from original_error

        assert exc_info.value.__cause__ is original_error
        assert str(exc_info.value) == "Wrapped error"
        assert exc_info.value.source == "test"
