"""Tests for Capital API route identifier migration.

Verify that the capital API routes:
1. Accept three optional identifier params (instrument_id, ticker, standard_ticker)
2. Resolve them via resolve_instrument_identifier
3. Pass the resulting int to the service layer
4. Return int instrument_id in response models
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_app._reexports import AmbiguousTickerError
from ditto_interfaces.api.utils.identifier import (
    resolve_identifier_for_api as _resolve_identifier,
)
from ditto_interfaces.models.capital import to_margin_list, to_valuation_list
from ditto_interfaces.models.common import APIResponse


@pytest.fixture
def margin_df() -> pl.DataFrame:
    """Create sample margin trading DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "trade_date": ["2024-01-15"],
            "margin_buy_balance": [1_500_000_000.0],
            "short_sell_balance": [200_000_000.0],
            "margin_buy_volume": [50_000],
            "short_sell_volume": [10_000],
        }
    )


@pytest.fixture
def valuation_df() -> pl.DataFrame:
    """Create sample valuation metrics DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "trade_date": ["2024-01-15"],
            "pe_ratio": [15.5],
            "pb_ratio": [2.3],
            "ps_ratio": [1.8],
            "dividend_yield": [3.2],
            "market_cap": [500_000_000_000.0],
        }
    )


@pytest.mark.unit
class TestResolveIdentifier:
    """Test the _resolve_identifier helper function."""

    def test_instrument_id_passthrough(self) -> None:
        """Pass instrument_id to MetadataService for resolution."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 1_000_001
        result = _resolve_identifier(
            mock_meta,
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
        )
        assert result == 1_000_001
        mock_meta.resolve_instrument_identifier.assert_called_once_with(
            instrument_id=1_000_001,
            standard_ticker=None,
            ticker=None,
            asof=None,
        )

    def test_standard_ticker_resolution(self) -> None:
        """Resolve standard_ticker via MetadataService."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 1_000_001
        result = _resolve_identifier(
            mock_meta,
            instrument_id=None,
            standard_ticker="000001.XSHE",
            ticker=None,
        )
        assert result == 1_000_001
        mock_meta.resolve_instrument_identifier.assert_called_once()

    def test_ticker_resolution(self) -> None:
        """Resolve ticker via MetadataService."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = 2_000_001
        result = _resolve_identifier(
            mock_meta,
            instrument_id=None,
            standard_ticker=None,
            ticker="510300",
        )
        assert result == 2_000_001

    def test_no_identifier_raises_422(self) -> None:
        """No identifier provided should raise HTTPException 422."""
        from fastapi import HTTPException

        mock_meta = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            _resolve_identifier(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker=None,
            )
        assert exc_info.value.status_code == 422

    def test_identifier_not_found_returns_none(self) -> None:
        """IdentifierNotFoundError resolved to None should return None."""
        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.return_value = None
        result = _resolve_identifier(
            mock_meta,
            instrument_id=None,
            standard_ticker=None,
            ticker="999999",
        )
        assert result is None

    def test_ambiguous_ticker_raises_400(self) -> None:
        """AmbiguousTickerError should raise HTTPException 400."""
        from fastapi import HTTPException

        mock_meta = MagicMock()
        mock_meta.resolve_instrument_identifier.side_effect = AmbiguousTickerError(
            ticker="000001", matches=[]
        )
        with pytest.raises(HTTPException) as exc_info:
            _resolve_identifier(
                mock_meta,
                instrument_id=None,
                standard_ticker=None,
                ticker="000001",
            )
        assert exc_info.value.status_code == 400


@pytest.mark.unit
class TestCapitalRouteResponseModels:
    """Test that capital route response models have int instrument_id."""

    def test_margin_response_has_int_instrument_id(
        self, margin_df: pl.DataFrame
    ) -> None:
        """Verify to_margin_list produces models with int instrument_id."""
        margins = to_margin_list(margin_df)
        assert len(margins) == 1
        assert isinstance(margins[0].instrument_id, int)
        assert margins[0].instrument_id == 1_000_001

    def test_valuation_response_has_int_instrument_id(
        self, valuation_df: pl.DataFrame
    ) -> None:
        """Verify to_valuation_list produces models with int instrument_id."""
        valuations = to_valuation_list(valuation_df)
        assert len(valuations) == 1
        assert isinstance(valuations[0].instrument_id, int)
        assert valuations[0].instrument_id == 1_000_001

    def test_margin_api_response_serialization(self, margin_df: pl.DataFrame) -> None:
        """Verify Margin model serializes instrument_id as int in JSON."""
        margins = to_margin_list(margin_df)
        response = APIResponse(data=margins)
        data = response.model_dump()
        assert isinstance(data["data"][0]["instrument_id"], int)
        assert data["data"][0]["instrument_id"] == 1_000_001

    def test_valuation_api_response_serialization(
        self, valuation_df: pl.DataFrame
    ) -> None:
        """Verify Valuation model serializes instrument_id as int in JSON."""
        valuations = to_valuation_list(valuation_df)
        response = APIResponse(data=valuations)
        data = response.model_dump()
        assert isinstance(data["data"][0]["instrument_id"], int)
        assert data["data"][0]["instrument_id"] == 1_000_001

    def test_empty_margin_returns_empty_list(self) -> None:
        """Empty DataFrame returns empty list."""
        df = pl.DataFrame()
        result = to_margin_list(df)
        assert result == []

    def test_empty_valuation_returns_empty_list(self) -> None:
        """Empty DataFrame returns empty list."""
        df = pl.DataFrame()
        result = to_valuation_list(df)
        assert result == []
