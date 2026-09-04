"""PIT contract tests for stock-status ingestion routing."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
from ditto_application.processes.ingestion.dataset_registry import (
    DailyFetchContext,
    default_dataset_registry,
)
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.catalog import default_dataset_metadata
from ditto_data.models import Dataset


def test_registry_passes_target_trade_date_to_stock_status_fetcher() -> None:
    market = MagicMock()
    market.fetch_stock_status.return_value = pl.DataFrame()
    registration = default_dataset_registry().require(Dataset.STOCK_STATUS)
    assert registration.daily_fetch_factory is not None
    context = DailyFetchContext(
        fetchers=SourceFetchers(
            metadata=MagicMock(),
            market=market,
            fundamental=MagicMock(),
            capital=MagicMock(),
            macro=MagicMock(),
        ),
        trade_date="2018-06-15",
        fetch_commodity_daily=MagicMock(),
        get_cached_index_codes=MagicMock(return_value=[]),
    )

    registration.daily_fetch_factory(context)()

    market.fetch_stock_status.assert_called_once_with("2018-06-15")


def test_stock_status_certification_cannot_start_before_provider_history() -> None:
    contract = default_dataset_metadata()["stock_status"].dataset_spec

    assert contract.raw_target_from == "2016-01-01"
    assert contract.certified_target_from == "2016-01-01"
    assert "tushare:bak_basic" in contract.provider_datasets
