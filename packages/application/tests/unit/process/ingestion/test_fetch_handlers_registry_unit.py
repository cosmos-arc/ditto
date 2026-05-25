"""Tests for registry-backed ingestion fetch handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.fetch_handlers import (
    build_daily_fetch_handlers,
    build_instrument_fetch_handlers,
)
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams


@pytest.fixture
def fetchers() -> SourceFetchers:
    metadata = MagicMock()
    market = MagicMock()
    fundamental = MagicMock()
    capital = MagicMock()
    macro = MagicMock()
    metadata.fetch_calendar.return_value = pl.DataFrame({"dataset": ["calendar"]})
    market.fetch_stock_daily.return_value = pl.DataFrame({"dataset": ["stock_daily"]})
    market.fetch_adj_factor_by_ticker.return_value = pl.DataFrame(
        {"dataset": ["adj_factor"]}
    )
    return SourceFetchers(
        metadata=metadata,
        market=market,
        fundamental=fundamental,
        capital=capital,
        macro=macro,
    )


@pytest.mark.unit
def test_daily_handlers_are_built_from_registry(
    fetchers: SourceFetchers,
) -> None:
    handlers = build_daily_fetch_handlers(
        fetchers,
        "2024-05-20",
        fetch_commodity_daily=lambda trade_date: pl.DataFrame(
            {"trade_date": [trade_date]}
        ),
        get_cached_index_codes=lambda: ["000300.SH"],
    )

    result = handlers[Dataset.CALENDAR]()

    assert result.to_dict(as_series=False) == {"dataset": ["calendar"]}
    fetchers.metadata.fetch_calendar.assert_called_once_with(
        "2024-01-01",
        "2024-12-31",
    )


@pytest.mark.unit
def test_instrument_handlers_are_built_from_registry(
    fetchers: SourceFetchers,
) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(
        fetchers,
        "000001.SZ",
        params,
    )
    result = handlers[Dataset.STOCK_DAILY]()

    assert result.to_dict(as_series=False) == {"dataset": ["stock_daily"]}
    fetchers.market.fetch_stock_daily.assert_called_once_with(
        source_ticker="000001.SZ",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )


@pytest.mark.unit
def test_stock_status_has_no_instrument_handler(
    fetchers: SourceFetchers,
) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(fetchers, "000001.SZ", params)

    assert Dataset.STOCK_STATUS not in handlers
