"""Tests for CommodityQueryFacade — Commodity/VIX 映射 + MarketService.list_bars."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app.query.commodity import CommodityQueryFacade
from ditto_data.models.source_codes import (
    COMMODITY_CODE_TO_INSTRUMENT_ID,
    VIX_CODE_TO_INSTRUMENT_ID,
)


class TestCommodityQueryFacadeMappings:
    """CommodityQueryFacade — 代码映射方法."""

    def test_get_valid_codes_includes_commodity_and_vix(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        codes = facade.get_valid_codes()

        assert "COMMOD_WTI" in codes
        assert "VIX_30D" in codes
        assert codes == set(COMMODITY_CODE_TO_INSTRUMENT_ID.keys()) | set(
            VIX_CODE_TO_INSTRUMENT_ID.keys()
        )

    def test_get_all_instrument_ids(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        ids = facade.get_all_instrument_ids()

        expected = list(COMMODITY_CODE_TO_INSTRUMENT_ID.values()) + list(
            VIX_CODE_TO_INSTRUMENT_ID.values()
        )
        assert ids == expected

    def test_code_to_instrument_id_commodity(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        result = facade.code_to_instrument_id("COMMOD_WTI")

        assert result == 5_000_001

    def test_code_to_instrument_id_vix(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        result = facade.code_to_instrument_id("VIX_30D")

        assert result == 5_100_001

    def test_code_to_instrument_id_raises_for_unknown(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        with pytest.raises(KeyError):
            facade.code_to_instrument_id("UNKNOWN")

    def test_instrument_id_to_code_commodity(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        result = facade.instrument_id_to_code(5_000_003)

        assert result == "COMMOD_GOLD"

    def test_instrument_id_to_code_vix(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        result = facade.instrument_id_to_code(5_100_001)

        assert result == "VIX_30D"

    def test_instrument_id_to_code_returns_none_for_unknown(self) -> None:
        service = MagicMock()
        facade = CommodityQueryFacade(market_service=service)

        result = facade.instrument_id_to_code(999_999)

        assert result is None


class TestCommodityQueryFacadeListBars:
    """CommodityQueryFacade.list_bars — 委托 MarketService, asset_class='commodity'."""

    def test_delegates_with_commodity_asset_class(self) -> None:
        service = MagicMock(spec=["list_bars"])
        service.list_bars.return_value = pl.DataFrame({"close": [75.0]})
        facade = CommodityQueryFacade(market_service=service)

        result = facade.list_bars(
            instrument_ids=[5_000_001],
            start="2024-01-01",
            end="2024-01-31",
            limit=200,
        )

        assert len(result) == 1
        service.list_bars.assert_called_once_with(
            instrument_ids=[5_000_001],
            start="2024-01-01",
            end="2024-01-31",
            asset_class="commodity",
            limit=200,
        )

    def test_delegates_with_none_optional_params(self) -> None:
        service = MagicMock(spec=["list_bars"])
        service.list_bars.return_value = pl.DataFrame()
        facade = CommodityQueryFacade(market_service=service)

        facade.list_bars(instrument_ids=[5_000_001])

        service.list_bars.assert_called_once_with(
            instrument_ids=[5_000_001],
            start=None,
            end=None,
            asset_class="commodity",
            limit=None,
        )
