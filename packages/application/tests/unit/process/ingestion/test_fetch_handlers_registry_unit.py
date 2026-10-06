"""Tests for registry-backed ingestion fetch handlers."""

from __future__ import annotations

from datetime import date
from typing import NamedTuple
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.fetch_handlers import (
    DailyContextCallbacks,
    build_daily_fetch_handlers,
    build_instrument_fetch_handlers,
)
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams


class _MockSources(NamedTuple):
    """组装好的 fetchers 供生产入口消费，mock 句柄供断言侧访问."""

    fetchers: SourceFetchers
    metadata: MagicMock
    market: MagicMock
    macro: MagicMock


@pytest.fixture
def sources() -> _MockSources:
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
    return _MockSources(
        fetchers=SourceFetchers(
            metadata=metadata,
            market=market,
            fundamental=fundamental,
            capital=capital,
            macro=macro,
        ),
        metadata=metadata,
        market=market,
        macro=macro,
    )


@pytest.mark.unit
def test_daily_handlers_are_built_from_registry(
    sources: _MockSources,
) -> None:
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2024-05-20",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda trade_date: pl.DataFrame(
                {"trade_date": [trade_date]}
            ),
            get_cached_index_codes=lambda: ["000300.SH"],
        ),
    )

    result = handlers[Dataset.CALENDAR]()

    assert result.to_dict(as_series=False) == {"dataset": ["calendar"]}
    sources.metadata.fetch_calendar.assert_called_once_with(
        "2024-01-01",
        # One forward month past the year boundary keeps a year-end Paper
        # handoff's next-session lookup cutoff-visible.
        "2025-01-31",
    )


@pytest.mark.unit
def test_instrument_handlers_are_built_from_registry(
    sources: _MockSources,
) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(
        sources.fetchers,
        "000001.SZ",
        params,
    )
    result = handlers[Dataset.STOCK_DAILY]()

    assert result.to_dict(as_series=False) == {"dataset": ["stock_daily"]}
    sources.market.fetch_stock_daily.assert_called_once_with(
        source_ticker="000001.SZ",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )


@pytest.mark.unit
def test_stock_status_has_no_instrument_handler(
    sources: _MockSources,
) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(sources.fetchers, "000001.SZ", params)

    assert Dataset.STOCK_STATUS not in handlers


@pytest.mark.unit
def test_macro_handler_fetches_the_certified_china_batch(
    sources: _MockSources,
) -> None:
    """Daily orchestration snapshots growth, prices, money, and survey data."""
    sources.macro.fetch_macro_indicators_by_codes.return_value = pl.DataFrame()
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2026-09-01",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda _trade_date: pl.DataFrame(),
            get_cached_index_codes=lambda: [],
        ),
    )

    handlers[Dataset.MACRO_INDICATORS]()

    sources.macro.fetch_macro_indicators_by_codes.assert_called_once_with(
        [
            "CN_GDP_YOY",
            "CN_CPI_YOY",
            "CN_PPI_YOY",
            "CN_M2_YOY",
            "CN_PMI_MFG",
            "CN_SF_FLOW_MONTH",
            "CN_SF_FLOW_CUM",
            "CN_SF_STOCK",
        ],
        "2015-01-01",
        "2026-09-01",
        observed_on=date.today(),
    )


@pytest.mark.unit
def test_macro_handler_preserves_non_tushare_provider_contract(
    sources: _MockSources,
) -> None:
    """FRED and future macro providers keep their provider-native daily API."""
    sources.macro.fetch_macro_indicators.return_value = pl.DataFrame()
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2026-09-01",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda _trade_date: pl.DataFrame(),
            get_cached_index_codes=lambda: [],
        ),
        source_name="fred",
    )

    handlers[Dataset.MACRO_INDICATORS]()

    sources.macro.fetch_macro_indicators.assert_called_once_with("2026-09-01")
    sources.macro.fetch_macro_indicators_by_codes.assert_not_called()


@pytest.mark.unit
def test_industry_mapping_handler_binds_partition_asof_and_retrieval_date(
    sources: _MockSources,
) -> None:
    """Historical partitions must not ingest the provider's current members."""
    sources.metadata.fetch_sw_industry_concepts.return_value = pl.DataFrame()
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2024-03-29",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda _trade_date: pl.DataFrame(),
            get_cached_index_codes=lambda: [],
        ),
    )

    handlers[Dataset.INDUSTRY_MAPPING]()

    sources.metadata.fetch_sw_industry_concepts.assert_called_once_with(
        asof_date="2024-03-29",
        level=1,
        knowledge_date=date.today(),
    )


@pytest.mark.unit
def test_industry_classification_handler_concats_sw_and_csrc(
    sources: _MockSources,
) -> None:
    """#517：分类快照 = 申万 L1 + 证监会两源拼接，级别统一 L 前缀。"""
    sources.metadata.fetch_sw_industry.return_value = pl.DataFrame(
        {
            "source_ticker": ["801010.SI"],
            "industry_name": ["农林牧渔"],
            "level": [1],
            "industry_level": [1],
        }
    )
    sources.metadata.fetch_csrc_industry.return_value = pl.DataFrame(
        {
            "industry_id": ["C39"],
            "industry_name": ["计算机、通信和其他电子设备制造业"],
            "industry_level": ["L2"],
            "source": ["csrc"],
        }
    )
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2026-09-01",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda _trade_date: pl.DataFrame(),
            get_cached_index_codes=lambda: [],
        ),
    )

    frame = handlers[Dataset.INDUSTRY_CLASSIFICATION]()

    assert frame.columns == [
        "industry_id",
        "industry_name",
        "industry_level",
        "knowledge_date",
        "classification_version",
        "source",
    ]
    rows = frame.sort("industry_id").to_dicts()
    assert [row["industry_id"] for row in rows] == ["801010.SI", "C39"]
    assert [row["industry_level"] for row in rows] == ["L1", "L2"]
    assert [row["source"] for row in rows] == ["sw", "csrc"]
    assert [row["classification_version"] for row in rows] == [
        "SW2021",
        "CSRC2012",
    ]


@pytest.mark.unit
def test_industry_classification_degrades_to_sw_on_csrc_auth_reject(
    sources: _MockSources,
) -> None:
    """#517：csrc 端点被 transport 权限拒（2002）时降级 SW-only 留痕."""
    from ditto_data.errors import SourceAuthenticationError

    sources.metadata.fetch_sw_industry.return_value = pl.DataFrame(
        {
            "source_ticker": ["801010.SI"],
            "industry_name": ["农林牧渔"],
            "level": [1],
            "industry_level": [1],
        }
    )
    sources.metadata.fetch_csrc_industry.side_effect = SourceAuthenticationError(
        message="token不对", source="tushare"
    )
    handlers = build_daily_fetch_handlers(
        sources.fetchers,
        "2026-09-01",
        DailyContextCallbacks(
            fetch_commodity_daily=lambda _trade_date: pl.DataFrame(),
            get_cached_index_codes=lambda: [],
        ),
    )

    frame = handlers[Dataset.INDUSTRY_CLASSIFICATION]()

    assert frame.height == 1
    assert frame.row(0, named=True)["source"] == "sw"
