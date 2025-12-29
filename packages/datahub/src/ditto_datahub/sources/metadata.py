"""Ingestion metadata models for incremental data fetching."""

from dataclasses import dataclass
from enum import Enum


class IncrementalMode(str, Enum):
    """Incremental fetch mode."""

    QUICK = "quick"  # Quick mode: date-level check
    PRECISE = "precise"  # Precise mode: data-level check


@dataclass(frozen=True)
class IngestionMetadata:
    """
    Metadata for data ingestion tracking.

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
