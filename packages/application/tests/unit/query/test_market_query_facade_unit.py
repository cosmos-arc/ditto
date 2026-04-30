"""Tests for MarketQueryFacade — encapsulates MarketService behind a clean API."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.query.market import MarketQueryFacade


class TestMarketQueryFacadeFindBars:
    """MarketQueryFacade.find_bars — 构建内部 MarketBarsQuery 并委托。"""

    def test_passes_primitives_to_service(self) -> None:
        service = MagicMock(spec=["find_bars"])
        service.find_bars.return_value = pl.DataFrame({"trade_date": ["2024-01-02"]})
        facade = MarketQueryFacade(market_service=service)

        result = facade.find_bars(
            instrument_ids=[1, 2],
            start="2024-01-01",
            end="2024-01-31",
            adj="qfq",
        )

        assert len(result) == 1
        # Verify service received a MarketBarsQuery with correct fields
        query_arg = service.find_bars.call_args[0][0]
        assert query_arg.instrument_ids == [1, 2]
        assert query_arg.start == "2024-01-01"
        assert query_arg.end == "2024-01-31"
        assert query_arg.adj.value == "qfq"

    def test_none_dates_uses_none(self) -> None:
        service = MagicMock(spec=["find_bars"])
        service.find_bars.return_value = pl.DataFrame()
        facade = MarketQueryFacade(market_service=service)

        facade.find_bars(instrument_ids=[1], start=None, end=None, adj="none")

        query_arg = service.find_bars.call_args[0][0]
        assert query_arg.start is None
        assert query_arg.end is None

    def test_invalid_adj_raises_value_error(self) -> None:
        service = MagicMock(spec=["find_bars"])
        facade = MarketQueryFacade(market_service=service)

        with pytest.raises(ValueError, match="adj"):
            facade.find_bars(instrument_ids=[1], start=None, end=None, adj="invalid")


class TestMarketQueryFacadeListBars:
    """MarketQueryFacade.list_bars — 带资产类别和 limit 的查询。"""

    def test_delegates_with_asset_class_and_limit(self) -> None:
        service = MagicMock(spec=["list_bars"])
        service.list_bars.return_value = pl.DataFrame()
        facade = MarketQueryFacade(market_service=service)

        facade.list_bars(
            instrument_ids=[100, 200],
            start="2024-01-01",
            end="2024-01-31",
            asset_class="fx",
            limit=500,
        )

        service.list_bars.assert_called_once_with(
            instrument_ids=[100, 200],
            start="2024-01-01",
            end="2024-01-31",
            asset_class="fx",
            limit=500,
        )


class TestMarketQueryFacadeGetConstituents:
    """MarketQueryFacade.get_constituents — 查询指数成分。"""

    def test_delegates_to_service(self) -> None:
        service = MagicMock(spec=["get_constituents"])
        service.get_constituents.return_value = pl.DataFrame(
            {"instrument_id": [1, 2], "weight": [0.5, 0.5]}
        )
        facade = MarketQueryFacade(market_service=service)

        result = facade.get_constituents(index_id=5, as_of_date="2024-06-30")

        service.get_constituents.assert_called_once_with(5, "2024-06-30")
        assert len(result) == 2
