"""Tests for Fundamental API route identifier migration.

Verify that the fundamental API routes:
1. Accept three optional identifier params (instrument_id, ticker, standard_ticker)
2. Resolve them via resolve_instrument_identifier
3. Pass the resulting int to the service layer
4. Return int instrument_id in response models
"""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_interfaces.api.utils.identifier import (
    resolve_identifier_for_api as _resolve_identifier,
)
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.fundamental import (
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)
from ditto_kernel import AmbiguousTickerError


@pytest.fixture
def financial_df() -> pl.DataFrame:
    """Create sample financial DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "report_date": ["2024-03-31"],
            "data": [{"total_assets": 1000000.0}],
        }
    )


@pytest.fixture
def dividend_df() -> pl.DataFrame:
    """Create sample dividend DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "announce_date": ["2024-03-31"],
            "dividend_type": ["cash"],
            "amount": [0.5],
        }
    )


@pytest.fixture
def corporate_action_df() -> pl.DataFrame:
    """Create sample corporate action DataFrame."""
    return pl.DataFrame(
        {
            "instrument_id": [1_000_001],
            "action_date": ["2024-03-31"],
            "action_type": ["split"],
            "description": ["1:2 stock split"],
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
class TestFundamentalRouteResponseModels:
    """Test that fundamental route response models have int instrument_id."""

    def test_financial_response_has_int_instrument_id(
        self, financial_df: pl.DataFrame
    ) -> None:
        """Verify to_financial_list produces models with int instrument_id."""
        financials = to_financial_list(financial_df, FinancialType.BALANCE_SHEET)
        assert len(financials) == 1
        assert isinstance(financials[0].instrument_id, int)
        assert financials[0].instrument_id == 1_000_001

    def test_dividend_response_has_int_instrument_id(
        self, dividend_df: pl.DataFrame
    ) -> None:
        """Verify to_dividend_list produces models with int instrument_id."""
        dividends = to_dividend_list(dividend_df)
        assert len(dividends) == 1
        assert isinstance(dividends[0].instrument_id, int)
        assert dividends[0].instrument_id == 1_000_001

    def test_corporate_action_response_has_int_instrument_id(
        self, corporate_action_df: pl.DataFrame
    ) -> None:
        """Verify to_corporate_action_list produces models with int instrument_id."""
        actions = to_corporate_action_list(corporate_action_df)
        assert len(actions) == 1
        assert isinstance(actions[0].instrument_id, int)
        assert actions[0].instrument_id == 1_000_001

    def test_financial_api_response_serialization(
        self, financial_df: pl.DataFrame
    ) -> None:
        """Verify Financial model serializes instrument_id as int in JSON."""
        financials = to_financial_list(financial_df, FinancialType.BALANCE_SHEET)
        response = APIResponse(data=financials)
        data = response.model_dump()
        assert isinstance(data["data"][0]["instrument_id"], int)
        assert data["data"][0]["instrument_id"] == 1_000_001

    def test_dividend_api_response_serialization(
        self, dividend_df: pl.DataFrame
    ) -> None:
        """Verify Dividend model serializes instrument_id as int in JSON."""
        dividends = to_dividend_list(dividend_df)
        response = APIResponse(data=dividends)
        data = response.model_dump()
        assert isinstance(data["data"][0]["instrument_id"], int)
        assert data["data"][0]["instrument_id"] == 1_000_001

    def test_corporate_action_api_response_serialization(
        self, corporate_action_df: pl.DataFrame
    ) -> None:
        """Verify CorporateAction model serializes instrument_id as int in JSON."""
        actions = to_corporate_action_list(corporate_action_df)
        response = APIResponse(data=actions)
        data = response.model_dump()
        assert isinstance(data["data"][0]["instrument_id"], int)
        assert data["data"][0]["instrument_id"] == 1_000_001

    def test_empty_financial_returns_empty_list(self) -> None:
        """Empty DataFrame returns empty list."""
        df = pl.DataFrame()
        result = to_financial_list(df, FinancialType.BALANCE_SHEET)
        assert result == []

    def test_empty_dividend_returns_empty_list(self) -> None:
        """Empty DataFrame returns empty list."""
        df = pl.DataFrame()
        result = to_dividend_list(df)
        assert result == []

    def test_empty_corporate_action_returns_empty_list(self) -> None:
        """Empty DataFrame returns empty list."""
        df = pl.DataFrame()
        result = to_corporate_action_list(df)
        assert result == []
