"""Dataset fetch handler builders backed by DatasetRegistry."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.processes.ingestion.dataset_registry import (
    DailyFetchContext,
    DatasetRegistry,
    InstrumentFetchContext,
    default_dataset_registry,
)
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "build_daily_fetch_handlers",
    "build_instrument_fetch_handlers",
]


def build_daily_fetch_handlers(
    fetchers: SourceFetchers,
    trade_date: str,
    *,
    fetch_commodity_daily: Callable[[str], pl.DataFrame],
    get_cached_index_codes: Callable[[], list[str]],
    registry: DatasetRegistry | None = None,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """Build date-level fetch handlers from the dataset registry."""
    active_registry = registry or default_dataset_registry()
    return active_registry.daily_fetch_handlers(
        DailyFetchContext(
            fetchers=fetchers,
            trade_date=trade_date,
            fetch_commodity_daily=fetch_commodity_daily,
            get_cached_index_codes=get_cached_index_codes,
        )
    )


def build_instrument_fetch_handlers(
    fetchers: SourceFetchers,
    source_ticker: str,
    params: InstrumentIngestParams,
    registry: DatasetRegistry | None = None,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """Build instrument-level fetch handlers from the dataset registry."""
    active_registry = registry or default_dataset_registry()
    return active_registry.instrument_fetch_handlers(
        InstrumentFetchContext(
            fetchers=fetchers,
            source_ticker=source_ticker,
            params=params,
        )
    )
