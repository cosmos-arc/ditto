"""
Data layer exception classes.

Following design document at docs/design/02_data_design.md

Note: DataError and IdentifierError are defined in ditto_kernel.exceptions
and imported privately here because Data-layer subclasses inherit from them.

This package is split by domain for maintainability. All symbols are
re-exported from this facade to preserve backward compatibility:
``from ditto_data.errors import ...`` continues to work unchanged.
"""

# --- calendar ---
from ditto_data.errors.calendar import (
    CalendarError,
    NotTradingDayError,
    TradingDateNotFoundError,
)

# --- instrument / identifier ---
from ditto_data.errors.instrument import (
    IdentifierNotFoundError,
    InstrumentIdNotFoundError,
)

# --- network / data source ---
from ditto_data.errors.network import (
    AuthError,
    DataSourceError,
    DataValidationError,
    NetworkError,
    SourceAuthenticationError,
    SourceConfigurationError,
    SourceFetchError,
    SourceRateLimitError,
    SourceTransformationError,
    convert_httpx_to_network_error,
)

# --- persistence / validation ---
from ditto_data.errors.persistence import (
    DataChangedError,
    DatasetNotFoundError,
    LateArrivalRejectedError,
    PartitionNotFoundError,
    PersistenceError,
    SchemaValidationError,
    ValidationError,
    WriteError,
)

__all__ = [
    "AuthError",
    "CalendarError",
    "DataChangedError",
    "DataSourceError",
    "DataValidationError",
    "DatasetNotFoundError",
    "IdentifierNotFoundError",
    "InstrumentIdNotFoundError",
    "LateArrivalRejectedError",
    "NetworkError",
    "NotTradingDayError",
    "PartitionNotFoundError",
    "PersistenceError",
    "SchemaValidationError",
    "SourceAuthenticationError",
    "SourceConfigurationError",
    "SourceFetchError",
    "SourceRateLimitError",
    "SourceTransformationError",
    "TradingDateNotFoundError",
    "ValidationError",
    "WriteError",
    "convert_httpx_to_network_error",
]
