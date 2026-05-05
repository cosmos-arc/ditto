"""Shared Parquet test helpers for E2E market fixtures."""

from __future__ import annotations

from pathlib import Path

from ditto_platform.foundation.storage import ParquetStore

MARKET_KEY_COLUMNS = ("instrument_id", "trade_date")
MARKET_DATE_COLUMN = "trade_date"
MARKET_INSTRUMENT_COLUMN = "instrument_id"


def market_parquet_store(data_root: Path) -> ParquetStore:
    """Create a market-owned store with explicit market columns."""
    return ParquetStore(
        data_root,
        key_columns=MARKET_KEY_COLUMNS,
        date_column=MARKET_DATE_COLUMN,
        instrument_column=MARKET_INSTRUMENT_COLUMN,
    )
