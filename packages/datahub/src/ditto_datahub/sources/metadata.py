"""Ingestion metadata models for data tracking."""

from dataclasses import dataclass
from enum import Enum


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
