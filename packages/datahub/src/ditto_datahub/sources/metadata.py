"""Ingestion metadata models for incremental data fetching."""

import warnings
from dataclasses import dataclass
from enum import Enum


class IncrementalMode(str, Enum):
    """
    Incremental fetch mode (deprecated, use new ingestion system).

    .. deprecated::
        **This enum is deprecated and will be removed in a future release.**

        Use ``IngestionCoordinator`` from
        ``ditto_server.ingestion.services.coordinator`` for unified
        ingestion with incremental logic, checksums, and metadata.

    """

    QUICK = "quick"  # Quick mode: date-level check
    PRECISE = "precise"  # Precise mode: data-level check

    def __init__(self, value: str) -> None:
        """Emit deprecation warning on instantiation."""
        super().__init__(value)
        warnings.warn(
            "IncrementalMode is deprecated. Use IngestionCoordinator from "
            "ditto_server.ingestion.services.coordinator for ingestion logic.",
            DeprecationWarning,
            stacklevel=2,
        )


@dataclass(frozen=True)
class IngestionMetadata:
    """
    Metadata for data ingestion tracking (deprecated, legacy compatibility).

    .. deprecated::
        **This dataclass is deprecated and will be removed in a future release.**

        Use ``IngestionLog`` and ``IngestionCursor`` from the new ingestion system
        (``ditto_datahub.stores.ingestion_log`` and ``ditto_datahub.stores.cursor``)
        for event-based ingestion tracking.

    Attributes:
        dataset: Dataset name (e.g., "etf_daily", "stock_daily")
        source: Data source identifier (e.g., "tushare")
        last_trade_date: Last successfully ingested trade date (YYYY-MM-DD format)
        last_checksum: Checksum of last ingested data
        last_rows: Number of rows in last ingestion
        last_updated_at: Timestamp of last update (ISO format)

    """

    dataset: str
    source: str
    last_trade_date: str | None  # ISO format string (YYYY-MM-DD) or None
    last_checksum: str | None
    last_rows: int
    last_updated_at: str

    def __post_init__(self) -> None:
        """Emit deprecation warning on instantiation."""
        warnings.warn(
            "IngestionMetadata is deprecated. Use IngestionLog and IngestionCursor "
            "from the new ingestion system (ditto_datahub.stores.ingestion_log and "
            "ditto_datahub.stores.cursor) for event-based tracking.",
            DeprecationWarning,
            stacklevel=2,
        )


# ============ New Ingestion System: Event Log + Cursor ============


class IngestionStatus(str, Enum):
    """Ingestion status for a specific trade date."""

    SUCCESS = "SUCCESS"  # Data successfully ingested
    FAIL = "FAIL"  # Ingestion failed (fetch error / DQ blocked / empty df)


@dataclass(frozen=True)
class IngestionLog:
    """
    Event log for a specific trade date (one record per date).

    Each trading day has exactly one record that can be updated on retry.
    Non-trading days are NOT recorded (check calendar table instead).

    Attributes:
        dataset: Dataset name (e.g., "stock_daily")
        source: Data source identifier (e.g., "tushare")
        trade_date: Trade date (YYYY-MM-DD)
        status: Current status (SUCCESS or FAIL)
        checksum: Data checksum (only when SUCCESS)
        rows: Number of rows (only when SUCCESS)
        error_code: Error code (only when FAIL)
        error_message: Error message (only when FAIL)
        attempts: Number of attempts (incremented on retry)
        first_attempt_at: First attempt timestamp (ISO format)
        last_attempt_at: Last attempt timestamp (ISO format)

    """

    dataset: str
    source: str
    trade_date: str
    status: IngestionStatus
    checksum: str | None = None
    rows: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: int = 1
    first_attempt_at: str | None = None
    last_attempt_at: str | None = None


@dataclass(frozen=True)
class IngestionCursor:
    """
    Cursor for tracking ingestion progress (redundant for fast queries).

    This is a denormalized cache for fast access to the last successful date.

    Attributes:
        dataset: Dataset name (e.g., "stock_daily")
        source: Data source identifier (e.g., "tushare")
        last_success: Last successful trade date (YYYY-MM-DD)
        last_attempted: Last attempted trade date (including FAIL) (YYYY-MM-DD)
        updated_at: Cursor update timestamp (ISO format)

    """

    dataset: str
    source: str
    last_success: str | None  # None if no successful ingestion yet
    last_attempted: str | None  # None if never attempted
    updated_at: str


# ============ New Ingestion System: Exceptions ============


class NotTradingDayError(Exception):
    """Raised when trying to ingest data for a non-trading day."""

    def __init__(self, trade_date: str) -> None:
        """
        Initialize NotTradingDayError.

        Args:
            trade_date: The non-trading date (YYYY-MM-DD).

        """
        self.trade_date = trade_date
        super().__init__(f"{trade_date} is not a trading day")


class DataChangedError(Exception):
    """Raised when data checksum changed and force=False."""

    def __init__(
        self,
        trade_date: str,
        old_checksum: str,
        new_checksum: str,
    ) -> None:
        """
        Initialize DataChangedError.

        Args:
            trade_date: The trade date (YYYY-MM-DD).
            old_checksum: Previous checksum.
            new_checksum: New checksum.

        """
        self.trade_date = trade_date
        self.old_checksum = old_checksum
        self.new_checksum = new_checksum
        super().__init__(
            f"Data changed for {trade_date}: checksum {old_checksum} → {new_checksum}. "
            "Use force=True to overwrite."
        )
