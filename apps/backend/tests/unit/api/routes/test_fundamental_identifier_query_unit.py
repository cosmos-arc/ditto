"""Tests for Fundamental API route response models.

Verify that the fundamental API routes return int instrument_id in
response models (identifier resolution itself is covered on the shared
resolve_identifier_for_api util by the capital route tests, #321 G46–G51).
"""

import polars as pl
import pytest
from ditto_apps.models.common import APIResponse
from ditto_apps.models.fundamental import (
    FinancialType,
    to_corporate_action_list,
    to_dividend_list,
    to_financial_list,
)


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
