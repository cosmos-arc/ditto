"""Dataset fetch handler builders backed by DatasetRegistry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    "DailyContextCallbacks",
    "build_daily_fetch_handlers",
    "build_instrument_fetch_handlers",
]


@dataclass(frozen=True)
class DailyContextCallbacks:
    """
    可选的日更取数回调（universe/声明源等宿主能力注入）.

    Attributes:
        fetch_commodity_daily: 商品日频取数（主源/冗余源合成）.
        get_cached_index_codes: 缓存的指数代码列表.
        fetch_etf_reference_config: 维护者确认的 ETF 参考声明读取（#408）.
        get_cached_etf_tickers: 注册表内 ETF 源代码列表（#522）.

    """

    fetch_commodity_daily: Callable[[str], pl.DataFrame]
    get_cached_index_codes: Callable[[], list[str]]
    fetch_etf_reference_config: Callable[[], pl.DataFrame] | None = None
    get_cached_etf_tickers: Callable[[], list[str]] | None = None


def build_daily_fetch_handlers(
    fetchers: SourceFetchers,
    trade_date: str,
    callbacks: DailyContextCallbacks,
    *,
    source_name: str = "tushare",
    registry: DatasetRegistry | None = None,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """Build date-level fetch handlers from the dataset registry."""
    active_registry = registry or default_dataset_registry()
    return active_registry.daily_fetch_handlers(
        DailyFetchContext(
            fetchers=fetchers,
            trade_date=trade_date,
            fetch_commodity_daily=callbacks.fetch_commodity_daily,
            get_cached_index_codes=callbacks.get_cached_index_codes,
            source_name=source_name,
            fetch_etf_reference_config=callbacks.fetch_etf_reference_config,
            get_cached_etf_tickers=callbacks.get_cached_etf_tickers,
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
