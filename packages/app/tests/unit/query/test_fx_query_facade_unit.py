"""Tests for FXQueryFacade — 封装 FX 映射和 MarketService.list_bars."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app.query.fx import FXQueryFacade
from ditto_data.models.source_codes import FX_CODE_TO_INSTRUMENT_ID


class TestFXQueryFacadeMappings:
    """FXQueryFacade — 代码映射方法."""

    def test_get_valid_pairs(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        pairs = facade.get_valid_pairs()

        assert pairs == set(FX_CODE_TO_INSTRUMENT_ID.keys())
        assert "USDCNH.FXCM" in pairs

    def test_get_all_instrument_ids(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        ids = facade.get_all_instrument_ids()

        assert ids == list(FX_CODE_TO_INSTRUMENT_ID.values())

    def test_pair_to_instrument_id(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        result = facade.pair_to_instrument_id("USDCNH.FXCM")

        assert result == 4_000_001

    def test_pair_to_instrument_id_raises_for_unknown(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        with pytest.raises(KeyError):
            facade.pair_to_instrument_id("UNKNOWN")

    def test_instrument_id_to_pair(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        result = facade.instrument_id_to_pair(4_000_001)

        assert result == "USDCNH.FXCM"

    def test_instrument_id_to_pair_returns_none_for_unknown(self) -> None:
        service = MagicMock()
        facade = FXQueryFacade(market_service=service)

        result = facade.instrument_id_to_pair(999_999)

        assert result is None


class TestFXQueryFacadeListBars:
    """FXQueryFacade.list_bars — 委托到 MarketService 并传入 asset_class='fx'."""

    def test_delegates_with_fx_asset_class(self) -> None:
        service = MagicMock(spec=["list_bars"])
        service.list_bars.return_value = pl.DataFrame({"close": [7.2]})
        facade = FXQueryFacade(market_service=service)

        result = facade.list_bars(
            instrument_ids=[4_000_001],
            start="2024-01-01",
            end="2024-01-31",
            limit=100,
        )

        assert len(result) == 1
        service.list_bars.assert_called_once_with(
            instrument_ids=[4_000_001],
            start="2024-01-01",
            end="2024-01-31",
            asset_class="fx",
            limit=100,
        )

    def test_delegates_with_none_optional_params(self) -> None:
        service = MagicMock(spec=["list_bars"])
        service.list_bars.return_value = pl.DataFrame()
        facade = FXQueryFacade(market_service=service)

        facade.list_bars(instrument_ids=[4_000_001])

        service.list_bars.assert_called_once_with(
            instrument_ids=[4_000_001],
            start=None,
            end=None,
            asset_class="fx",
            limit=None,
        )
