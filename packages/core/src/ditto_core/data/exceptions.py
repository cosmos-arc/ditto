"""Custom exceptions for the data module."""

from typing import Any


class DataSourceError(Exception):
    """Base exception for data source errors."""

    def __init__(
        self,
        message: str,
        source: str | None = None,
        symbol: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize DataSourceError."""
        super().__init__(message)
        self.message = message
        self.source = source
        self.symbol = symbol
        self.extra = kwargs


class NetworkError(DataSourceError):
    """Network-related errors that can be retried."""

    pass


class ValidationError(DataSourceError):
    """Data validation errors."""

    pass


class ConfigurationError(DataSourceError):
    """Configuration-related errors."""

    pass


class AuthenticationError(DataSourceError):
    """Authentication/authorization errors."""

    pass


class RateLimitError(DataSourceError):
    """Rate limiting errors."""

    pass
